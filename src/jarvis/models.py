from __future__ import annotations

from dataclasses import dataclass

from cursor_sdk import ModelParameterDefinition, ModelParameterValue, ModelSelection, SDKModel

_EFFORT_PARAM_IDS = ("effort", "reasoning", "reasoning_effort")
_FAST_PARAM_ID = "fast"


@dataclass(frozen=True)
class EffortOption:
    label: str
    params: tuple[ModelParameterValue, ...]
    replace: bool = False

    def as_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.id, item.value) for item in self.params)


def format_params(pairs: tuple[tuple[str, str], ...]) -> str:
    if not pairs:
        return "по умолчанию"
    return " · ".join(_human_param(key, value) for key, value in pairs)


def format_selection(model_id: str | None, pairs: tuple[tuple[str, str], ...]) -> str:
    if not model_id:
        return "не задана"
    return f"{model_id} · {format_params(pairs)}"


def selection_from_stored(
    model_id: str,
    pairs: tuple[tuple[str, str], ...],
) -> ModelSelection:
    return ModelSelection(
        id=model_id,
        params=tuple(ModelParameterValue(id=key, value=value) for key, value in pairs),
    )


def stored_from_selection(selection: ModelSelection) -> tuple[str, tuple[tuple[str, str], ...]]:
    return selection.id, tuple((item.id, item.value) for item in selection.params)


def merge_params(
    current: tuple[tuple[str, str], ...],
    option: EffortOption,
) -> tuple[tuple[str, str], ...]:
    if option.replace or not option.params:
        return option.as_pairs()
    merged = dict(current)
    merged.update(option.as_pairs())
    return tuple(merged.items())


def effort_options(model: SDKModel) -> list[EffortOption]:
    """Buttons must show effort values, not the model display name.

    Cursor often repeats the model name on every variant. Prefer the
    effort/reasoning parameter list; fall back to uniquely named variants.
    """
    options: list[EffortOption] = [
        EffortOption("По умолчанию", (), replace=True),
    ]
    effort_def = _param(model, _EFFORT_PARAM_IDS)
    fast_def = _param(model, (_FAST_PARAM_ID,))

    if effort_def and effort_def.values:
        for value in effort_def.values:
            label = (value.display_name or value.value).strip() or value.value
            options.append(
                EffortOption(
                    label[:64],
                    (ModelParameterValue(id=effort_def.id, value=value.value),),
                )
            )
        if fast_def:
            options.append(
                EffortOption("Fast вкл", (ModelParameterValue(id=_FAST_PARAM_ID, value="true"),))
            )
            options.append(
                EffortOption("Fast выкл", (ModelParameterValue(id=_FAST_PARAM_ID, value="false"),))
            )
        return options

    if fast_def and fast_def.values:
        for value in fast_def.values:
            label = "Fast" if value.value == "true" else "Обычный"
            options.append(
                EffortOption(
                    label,
                    (ModelParameterValue(id=_FAST_PARAM_ID, value=value.value),),
                    replace=True,
                )
            )
        return options

    if model.variants and _variant_names_are_unique(model):
        for variant in model.variants:
            label = variant.display_name.strip()[:64]
            if variant.is_default:
                label = f"{label} · default"
            options.append(EffortOption(label, tuple(variant.params), replace=True))
        return options

    if model.variants:
        seen: set[tuple[tuple[str, str], ...]] = set()
        for variant in model.variants:
            pairs = tuple((item.id, item.value) for item in variant.params)
            if pairs in seen:
                continue
            seen.add(pairs)
            label = format_params(pairs)
            if variant.is_default:
                label = f"{label} · default"
            options.append(EffortOption(label[:64], tuple(variant.params), replace=True))
        return options

    return options if len(options) > 1 else []


def _param(model: SDKModel, ids: tuple[str, ...]) -> ModelParameterDefinition | None:
    wanted = {item.lower() for item in ids}
    for item in model.parameters:
        if item.id.lower() in wanted:
            return item
    return None


def _variant_names_are_unique(model: SDKModel) -> bool:
    names = [variant.display_name.strip() for variant in model.variants if variant.display_name]
    if len(names) != len(model.variants) or len(set(names)) != len(names):
        return False
    model_name = (model.display_name or "").strip().lower()
    return not all(name.lower() == model_name for name in names)


def _human_param(key: str, value: str) -> str:
    lowered = key.lower()
    if lowered == _FAST_PARAM_ID:
        return "Fast" if value == "true" else "без Fast"
    if lowered in {"thinking"}:
        return "Thinking" if value == "true" else "без Thinking"
    if lowered in _EFFORT_PARAM_IDS:
        return value
    return f"{key}={value}"
