import json
from types import SimpleNamespace

import pytest

from codex_cli import (
    CodexCLICompletion,
    CodexCLIError,
    CodexCLIToolCall,
    _codex_image_args,
    _last_jsonl_agent_message,
    _output_schema,
    _parse_completion,
    _planner_prompt,
    complete_with_codex_cli,
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


def test_codex_image_args_normalizes_large_source_png(tmp_path):
    from PIL import Image

    source = tmp_path / "source.png"
    Image.new("RGB", (1600, 1200), (20, 40, 60)).save(source)

    args = _codex_image_args(
        [{"role": "user", "content": [{"type": "image_url", "image_url": {
            "url": source.as_uri(),
        }}]}],
        tmp_path / "codex",
    )

    assert args[:1] == ["--image"]
    normalized = Image.open(args[1])
    assert normalized.format == "JPEG"
    assert normalized.size == (1024, 768)


def test_last_jsonl_agent_message_recovers_structured_output():
    stdout = b"\n".join([
        b'{"type":"turn.started"}',
        b'{"type":"item.completed","item":{"type":"agent_message","text":"{\\"content\\":\\"OK\\"}"}}',
        b'{"type":"turn.completed"}',
    ])

    assert _last_jsonl_agent_message(stdout) == '{"content":"OK"}'


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [
    {"type": "error", "message": "Model unavailable"},
    {"type": "turn.failed", "error": {"message": "Model unavailable"}},
    {"type": "turn.failed", "error": {"message": json.dumps({
        "type": "error", "status": 400, "error": {"message": "Model unavailable"},
    })}},
    None,
])
async def test_cli_failure_reports_jsonl_error_or_stderr(monkeypatch, tmp_path, event):
    stdout = b'not json\n[]\n{"type":"turn.started"}\n'
    if event is not None:
        stdout += json.dumps(event).encode()

    async def communicate(prompt):
        return stdout, b"CLI diagnostic"

    async def create_process(*args, **kwargs):
        return SimpleNamespace(returncode=1, communicate=communicate)

    monkeypatch.setattr("codex_cli._codex_executable", lambda: "codex")
    monkeypatch.setattr("codex_cli.asyncio.create_subprocess_exec", create_process)
    expected = "Model unavailable" if event is not None else "CLI diagnostic"
    with pytest.raises(CodexCLIError, match=expected):
        await complete_with_codex_cli(
            model="gpt-6.1-sol", messages=[], working_directory=str(tmp_path),
        )


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


def test_parse_completion_drops_duplicate_tool_call_ids():
    result = _parse_completion(json.dumps({
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "name": "lookup_weather",
                "arguments_json": '{"city": "Paris"}',
            },
            {
                "id": "call_1",
                "name": "lookup_weather",
                "arguments_json": '{"city": "Paris"}',
            },
        ],
        "finish_reason": "tool_calls",
    }), {"lookup_weather"})

    assert [call.id for call in result.tool_calls] == ["call_1"]


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
