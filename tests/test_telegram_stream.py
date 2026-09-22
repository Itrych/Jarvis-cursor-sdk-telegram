from __future__ import annotations

import unittest
from types import SimpleNamespace

from jarvis.telegram_stream import LiveTelegramMessage, append_stream_text


class StreamTextTests(unittest.TestCase):
    def test_glued_sentences_split_on_newline(self) -> None:
        glued = (
            "Соберу сводку с диаграммами в PDF.Беру эталонную таблицу NASA NSSDC "
            "и уточняю составы.В системе конфликт NumPy и Matplotlib, поэтому "
            "поставлю отдельное окружение.PDF готов."
        )
        text = append_stream_text("", glued)
        self.assertIn("в PDF.\nБеру эталонную", text)
        self.assertIn("составы.\nВ системе конфликт", text)
        self.assertIn("окружение.\nPDF готов.", text)

    def test_separate_deltas_break_after_period(self) -> None:
        text = append_stream_text("", "PDF собрался.")
        text = append_stream_text(text, "Просматриваю ключевые страницы.")
        self.assertEqual(
            text,
            "PDF собрался.\nПросматриваю ключевые страницы.",
        )

    def test_force_break_after_tool(self) -> None:
        text = append_stream_text("Ищу таблицу.", "Пишу генератор.", force_break=True)
        self.assertEqual(text, "Ищу таблицу.\nПишу генератор.")

    def test_live_message_applies_glued_deltas(self) -> None:
        live = LiveTelegramMessage.__new__(LiveTelegramMessage)
        live._text = ""
        live._tools = []
        live._thinking = False
        live._pending_break = False
        live._status = "работает"
        live._dirty = False
        live._project_name = "Vsya4ina"
        live.apply_delta(SimpleNamespace(type="text-delta", text="PDF.Беру таблицу."))
        live.apply_delta(SimpleNamespace(type="tool-call-started", tool_call={"name": "Read"}))
        live.apply_delta(SimpleNamespace(type="text-delta", text="Пишу генератор."))
        self.assertEqual(live._text, "PDF.\nБеру таблицу.\nПишу генератор.")
        rendered = live.render()
        self.assertIn("PDF.\nБеру таблицу.\nПишу генератор.", rendered)


if __name__ == "__main__":
    unittest.main()
