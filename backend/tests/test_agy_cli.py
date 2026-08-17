import json

import pytest

from agy_cli import (
    AgyCLICompletion,
    AgyCLIError,
    AgyCLIToolCall,
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
        "status": "SUCCESS",
        "structured_output": {
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "name": "lookup_weather",
                "arguments_json": '{"city": "Paris"}',
            }],
            "finish_reason": "tool_calls",
        },
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "thinking_tokens": 10,
        },
    }), {"lookup_weather"})
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup_weather"
    assert result.tool_calls[0].arguments == '{"city":"Paris"}'
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 20
    assert result.reasoning_tokens == 10


def test_parse_completion_handles_dict_arguments():
    result = _parse_completion(json.dumps({
        "status": "SUCCESS",
        "structured_output": {
            "content": "Done",
            "tool_calls": [{
                "id": "call_1",
                "name": "lookup_weather",
                "arguments_json": {"city": "Tokyo"},
            }],
            "finish_reason": "tool_calls",
        },
    }), {"lookup_weather"})
    assert result.tool_calls[0].arguments == '{"city":"Tokyo"}'


def test_parse_completion_rejects_unknown_tool():
    with pytest.raises(AgyCLIError, match="unknown Stimma tool"):
        _parse_completion(json.dumps({
            "status": "SUCCESS",
            "structured_output": {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "name": "not_real",
                    "arguments_json": "{}",
                }],
                "finish_reason": "tool_calls",
            },
        }), {"lookup_weather"})


@pytest.mark.asyncio
async def test_llm_completion_routes_agy_provider_through_cli(monkeypatch):
    async def fake_complete(**kwargs):
        assert kwargs["model"] == "Gemini 3.1 Pro (High)"
        assert kwargs["reasoning_level"] == "high"
        assert kwargs["working_directory"] is None
        return AgyCLICompletion(
            tool_calls=[AgyCLIToolCall(
                id="call_1",
                name="lookup_weather",
                arguments='{"city":"Paris"}',
            )],
            prompt_tokens=15,
            completion_tokens=5,
            reasoning_tokens=3,
        )

    monkeypatch.setattr("agy_cli.complete_with_agy_cli", fake_complete)
    response = await llm_completion(
        LLMEndpointConfig(
            url="agy-cli://local",
            model="Gemini 3.1 Pro (High)",
            provider_kind="agy_cli",
            reasoning_level="high",
        ),
        [{"role": "user", "content": "Weather?"}],
        tools=[{
            "type": "function",
            "function": {"name": "lookup_weather", "parameters": {}},
        }],
    )

    assert response.finish_reason == FinishReason.TOOL_CALLS
    assert response.tool_calls[0].name == "lookup_weather"
    assert response.usage.prompt_tokens == 15
    assert response.usage.completion_tokens == 5
    assert response.usage.reasoning_tokens == 3
    assert response.usage.total_tokens == 20
