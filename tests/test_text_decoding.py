from __future__ import annotations

from camo.texts.decoding import decode_text_bytes


def test_decode_text_bytes_handles_utf16_bom() -> None:
    raw = "书名：笑傲江湖".encode("utf-16")

    text, encoding = decode_text_bytes(raw)

    assert text == "书名：笑傲江湖"
    assert encoding == "utf-16"
