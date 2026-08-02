from __future__ import annotations

import pytest

from octocoder.voice import extract_speakable_text, split_speakable_text


def test_extract_speakable_text_removes_code_and_markdown() -> None:
    source = """# 完成

- 已修改 **配置**，详见 [文档](https://example.test/docs)。

```python
secret = 'do not speak'
```

运行 `uv run pytest` 即可。 https://example.test/raw
"""
    result = extract_speakable_text(source)
    assert "secret" not in result
    assert "https://" not in result
    assert "**" not in result
    assert "`" not in result
    assert "已修改 配置" in result
    assert "uv run pytest" in result


def test_extract_code_only_reply_is_empty() -> None:
    assert extract_speakable_text("```ts\nconst value = 1;\n```") == ""


def test_split_prefers_chinese_and_english_sentence_boundaries() -> None:
    chunks = split_speakable_text("第一句话。第二句话！ Third sentence. Fourth?", max_chars=18)
    assert chunks == ["第一句话。 第二句话！", "Third sentence.", "Fourth?"]


def test_split_hard_wraps_unbroken_text() -> None:
    chunks = split_speakable_text("x" * 25, max_chars=10)
    assert [len(chunk) for chunk in chunks] == [10, 10, 5]


def test_split_never_exceeds_limit() -> None:
    text = "这是一个句子。" * 1000
    chunks = split_speakable_text(text, max_chars=100)
    assert chunks
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks).replace(" ", "") == text


def test_split_validates_limit() -> None:
    with pytest.raises(ValueError):
        split_speakable_text("hello", max_chars=0)
