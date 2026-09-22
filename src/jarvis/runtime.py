from __future__ import annotations

import logging
from html import escape
from pathlib import Path

from aiogram import Bot
from cursor_sdk import (
    AgentBusyError,
    AgentNotFoundError,
    AgentOptions,
    AsyncAgent,
    AsyncClient,
    CursorAgentError,
    LocalAgentOptions,
    ModelSelection,
    SDKModel,
    SendOptions,
)

from jarvis.config import Settings
from jarvis.models import (
    EffortOption,
    effort_options,
    format_selection,
    selection_from_stored,
    stored_from_selection,
)
from jarvis.store import Project, Store
from jarvis.telegram_stream import LiveTelegramMessage

log = logging.getLogger(__name__)


class ProjectBusyError(RuntimeError):
    pass


class AgentRuntime:
    def __init__(self, settings: Settings, store: Store) -> None:
        self._settings = settings
        self._store = store
        self._client: AsyncClient | None = None
        self._agents: dict[int, AsyncAgent] = {}
        self._busy: set[int] = set()
        self._active_runs: dict[int, object] = {}
        self._model_cache: list[SDKModel] = []
        self._effort_cache: list[EffortOption] = []

    @property
    def client(self) -> AsyncClient | None:
        return self._client

    def is_busy(self, project_id: int) -> bool:
        return project_id in self._busy

    async def start(self) -> None:
        await self._ensure_client()

    async def stop(self) -> None:
        for project_id, run in list(self._active_runs.items()):
            cancel = getattr(run, "cancel", None)
            supports = getattr(run, "supports", None)
            try:
                if callable(supports) and supports("cancel") and callable(cancel):
                    await cancel()
            except Exception:
                log.exception("cancel on shutdown failed project_id=%s", project_id)
        self._active_runs.clear()
        for project_id, agent in list(self._agents.items()):
            try:
                await agent.close()
            except Exception:
                log.exception("agent close failed project_id=%s", project_id)
        self._agents.clear()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_models(self) -> list[SDKModel]:
        client = await self._ensure_client()
        models = [
            item
            for item in await client.models.list(api_key=self._settings.cursor_api_key)
            if item.id
        ]
        self._model_cache = models
        for item in models:
            log.debug(
                "catalog model=%s params=%s variants=%s",
                item.id,
                [(param.id, [value.value for value in param.values]) for param in item.parameters],
                [variant.display_name for variant in item.variants],
            )
        return models

    def model_by_index(self, index: int) -> SDKModel | None:
        if 0 <= index < len(self._model_cache):
            return self._model_cache[index]
        return None

    def model_by_id(self, model_id: str) -> SDKModel | None:
        for item in self._model_cache:
            if item.id == model_id:
                return item
        return None

    def prepare_effort_options(self, model: SDKModel) -> list[EffortOption]:
        self._effort_cache = effort_options(model)
        return self._effort_cache

    def effort_by_index(self, index: int) -> EffortOption | None:
        if 0 <= index < len(self._effort_cache):
            return self._effort_cache[index]
        return None

    def selection_for(self, project: Project, model_id: str | None = None) -> ModelSelection:
        chosen = model_id or project.model or self._settings.default_model
        pairs = project.model_params
        if model_id and project.model and model_id != project.model:
            pairs = ()
        return selection_from_stored(chosen, pairs)

    async def run_prompt(
        self,
        bot: Bot,
        chat_id: int,
        project: Project,
        prompt: str,
        *,
        model: str | None = None,
    ) -> None:
        if not self._settings.cursor_ready:
            await bot.send_message(chat_id, "CURSOR_API_KEY не задан. Пропиши его в .env.")
            return
        if project.id in self._busy:
            raise ProjectBusyError(f"Проект {project.name} уже выполняет задачу.")
        self._busy.add(project.id)
        live = LiveTelegramMessage(bot, chat_id, project.name)
        label = "сбой"
        try:
            await live.flush(force=True)
            selection = self.selection_for(project, model)
            agent = await self._get_agent(project, selection)
            send_options = SendOptions(
                model=selection,
                on_delta=live.apply_delta,
            )
            log.info(
                "send project=%s agent=%s model=%s",
                project.name,
                agent.agent_id,
                format_selection(selection.id, tuple((p.id, p.value) for p in selection.params)),
            )
            run = await agent.send(prompt, send_options)
            self._active_runs[project.id] = run
            log.info("run started id=%s project=%s", run.id, project.name)
            result = await run.wait()
            live.replace_text_if_empty(result.result or "")
            status = str(result.status)
            if status == "finished":
                label = "готово"
            elif status == "cancelled":
                label = "отменено"
            else:
                label = f"ошибка ({status})"
            if agent.model is not None:
                model_id, pairs = stored_from_selection(agent.model)
                await self._store.update_agent(
                    project.id,
                    agent.agent_id,
                    model_id,
                    model_params=pairs or project.model_params,
                )
        except AgentBusyError:
            label = "агент занят"
            await bot.send_message(chat_id, "Агент занят. /stop и повтори.")
        except CursorAgentError as exc:
            label = "не запустился"
            log.exception("cursor agent error project=%s", project.name)
            await bot.send_message(
                chat_id,
                f"Cursor SDK: {escape(str(exc))}\nretryable={getattr(exc, 'is_retryable', False)}",
            )
        except Exception:
            label = "сбой"
            log.exception("run failed project=%s", project.name)
            await bot.send_message(chat_id, "Сбой прогона. Подробности в логе Jarvis.")
        finally:
            await live.close(label)
            self._active_runs.pop(project.id, None)
            self._busy.discard(project.id)

    async def cancel(self, project_id: int) -> bool:
        run = self._active_runs.get(project_id)
        if run is None:
            return False
        supports = getattr(run, "supports", None)
        cancel = getattr(run, "cancel", None)
        if callable(supports) and not supports("cancel"):
            return False
        if not callable(cancel):
            return False
        await cancel()
        return True

    async def _ensure_client(self) -> AsyncClient:
        if self._client is not None:
            return self._client
        workspace = Path(self._settings.bridge_workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        state_root = self._settings.repo_root / "data" / "bridge"
        state_root.mkdir(parents=True, exist_ok=True)
        log.info("launching cursor-sdk-bridge workspace=%s", workspace)
        self._client = await AsyncClient.launch_bridge(
            workspace=str(workspace),
            state_root=str(state_root),
        )
        return self._client

    async def _get_agent(self, project: Project, selection: ModelSelection) -> AsyncAgent:
        cached = self._agents.get(project.id)
        if cached is not None:
            return cached
        client = await self._ensure_client()
        cwd = str(Path(project.path))
        options = AgentOptions(
            model=selection,
            api_key=self._settings.cursor_api_key,
            name=f"jarvis-{project.name}",
            local=LocalAgentOptions(cwd=cwd),
        )
        agent: AsyncAgent | None = None
        if project.agent_id:
            try:
                agent = await client.agents.resume(project.agent_id, options)
                log.info("resumed agent %s for %s", agent.agent_id, project.name)
            except (AgentNotFoundError, CursorAgentError) as exc:
                log.warning("resume failed for %s: %s — creating new agent", project.name, exc)
                agent = None
        if agent is None:
            agent = await client.agents.create(
                model=selection,
                api_key=self._settings.cursor_api_key,
                name=f"jarvis-{project.name}",
                local=LocalAgentOptions(cwd=cwd),
            )
            log.info("created agent %s for %s", agent.agent_id, project.name)
        await self._store.update_agent(
            project.id,
            agent.agent_id,
            selection.id,
            model_params=tuple((item.id, item.value) for item in selection.params),
        )
        self._agents[project.id] = agent
        return agent
