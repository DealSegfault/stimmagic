import json

import pytest

from codex_cli import (
    CodexCLICompletion,
    CodexCLIError,
    CodexCLIToolCall,
    _output_schema,
    _parse_completion,
    _planner_prompt,
)
from config import LLMEndpointConfig
from llm import FinishReason, llm_completion


def test_output_schema_restricts_tool_names():
    schema = _output_schema(["lookup_weather", "finish"])
    name_schema = schema["properties"]["tool_calls"]["items"]["properties"]["name"]
    assert name_schema["enum"] == ["finish", "lookup_weather"]


def test_planner_prompt_contains_history_and_tools_without_inline_binary():
    prompt = _planner_prompt(
        [{"role": "user", "content": "data:image/png;base64," + "a" * 5000}],
        [{"type": "function", "function": {"name": "generate", "parameters": {}}}],
    )
    assert "inline binary asset omitted" in prompt
    assert '"name": "generate"' in prompt
    assert "a" * 5000 not in prompt


def test_parse_completion_normalizes_arguments():
    result = _parse_completion(json.dumps({
        "content": "",
        "tool_calls": [{
            "id": "call_1",
            "name": "lookup_weather",
            "arguments_json": '{"city": "Paris"}',
        }],
        "finish_reason": "tool_calls",
    }), {"lookup_weather"})
    assert result.tool_calls[0].arguments == '{"city":"Paris"}'


def test_parse_completion_rejects_unknown_tool():
    with pytest.raises(CodexCLIError, match="unknown Stimma tool"):
        _parse_completion(json.dumps({
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "name": "not_real",
                "arguments_json": "{}",
            }],
            "finish_reason": "tool_calls",
        }), {"lookup_weather"})


@pytest.mark.asyncio
async def test_llm_completion_routes_codex_provider_through_cli(monkeypatch):
    async def fake_complete(**kwargs):
        assert kwargs["model"] == "gpt-5.6-luna"
        assert kwargs["reasoning_level"] == "low"
        assert kwargs["working_directory"] is None
        return CodexCLICompletion(
            tool_calls=[CodexCLIToolCall(
                id="call_1",
                name="lookup_weather",
                arguments='{"city":"Paris"}',
            )],
            prompt_tokens=12,
            completion_tokens=4,
        )

    monkeypatch.setattr("codex_cli.complete_with_codex_cli", fake_complete)
    response = await llm_completion(
        LLMEndpointConfig(
            url="codex-cli://local",
            model="gpt-5.6-luna",
            provider_kind="codex_cli",
            reasoning_level="low",
        ),
        [{"role": "user", "content": "Weather?"}],
        tools=[{
            "type": "function",
            "function": {"name": "lookup_weather", "parameters": {}},
        }],
    )

    assert response.finish_reason == FinishReason.TOOL_CALLS
    assert response.tool_calls[0].name == "lookup_weather"
    assert response.usage.total_tokens == 16
