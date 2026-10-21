"""Tests for the XML tag parser."""

import pytest
from praxis_agent_runtime.parsers.tag_parser import extract_tool_calls, format_tool_response


class TestExtractToolCalls:
    def test_no_tool_calls(self):
        text = "Just a normal response with no tools."
        clean, calls = extract_tool_calls(text)
        assert clean == text
        assert calls == []

    def test_single_tool_call(self):
        text = (
            "I will read that file. "
            '<tool_call>{"name": "fs_read_file", "arguments": {"path": "x.py"}}</tool_call>'
        )
        clean, calls = extract_tool_calls(text)
        assert clean == "I will read that file."
        assert len(calls) == 1
        assert calls[0].name == "fs_read_file"
        assert calls[0].arguments == {"path": "x.py"}

    def test_multiple_tool_calls(self):
        text = (
            '<tool_call>{"name": "a", "arguments": {}}</tool_call> '
            "middle text "
            '<tool_call>{"name": "b", "arguments": {"x": 1}}</tool_call>'
        )
        clean, calls = extract_tool_calls(text)
        assert "middle text" in clean
        assert len(calls) == 2
        assert calls[0].name == "a"
        assert calls[1].name == "b"

    def test_tool_call_no_arguments(self):
        text = '<tool_call>{"name": "get_time"}</tool_call>'
        _, calls = extract_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].arguments == {}

    def test_invalid_json_raises(self):
        text = "<tool_call>not valid json</tool_call>"
        with pytest.raises(ValueError, match="Invalid JSON"):
            extract_tool_calls(text)

    def test_missing_name_raises(self):
        text = '<tool_call>{"arguments": {"x": 1}}</tool_call>'
        with pytest.raises(ValueError, match="missing 'name'"):
            extract_tool_calls(text)

    def test_multiline_tool_call(self):
        text = """Here is the result.
<tool_call>
{
    "name": "fs_write_file",
    "arguments": {
        "path": "out.txt",
        "content": "hello"
    }
}
</tool_call>"""
        clean, calls = extract_tool_calls(text)
        assert clean == "Here is the result."
        assert calls[0].name == "fs_write_file"
        assert calls[0].arguments["content"] == "hello"


class TestFormatToolResponse:
    def test_basic_format(self):
        result = format_tool_response("fs_read_file", '{"success": true}')
        assert '<tool_response name="fs_read_file">' in result
        assert '{"success": true}' in result
        assert "</tool_response>" in result
