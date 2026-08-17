import asyncio
import json
import pytest
from types import SimpleNamespace

from agent.v2.service import _execute_tool_call, _is_generation_tool_call
from database import Chat, ChatItem


@pytest.mark.asyncio
async def test_generation_detection_for_both_agy_and_codex():
    assert _is_generation_tool_call("bash", json.dumps({"command": "/Users/mac/.local/bin/agy --print 'cat'"})) is True
    assert _is_generation_tool_call("bash", json.dumps({"command": "/Users/mac/.local/bin/codex exec 'dog'"})) is True
    assert _is_generation_tool_call("bash", json.dumps({"command": "ls -la"})) is False


@pytest.mark.asyncio
async def test_execute_tool_call_with_session_lock_concurrent(session, async_engine, tmp_path):
    # Setup test chat and tool call items
    chat = Chat(name="Test Parallel Tool Calls")
    session.add(chat)
    await session.commit()
    await session.refresh(chat)

    call1 = ChatItem(
        chat_id=chat.id,
        item_type="tool_call",
        tool_name="bash",
        tool_call_id="call_1",
        tool_args=json.dumps({"command": "echo 'agy result'"}),
    )
    call2 = ChatItem(
        chat_id=chat.id,
        item_type="tool_call",
        tool_name="bash",
        tool_call_id="call_2",
        tool_args=json.dumps({"command": "echo 'codex result'"}),
    )
    session.add(call1)
    session.add(call2)
    await session.commit()

    ws_broadcasts = []
    ws_manager = SimpleNamespace(
        broadcast=lambda event, data: asyncio.sleep(0, result=ws_broadcasts.append((event, data)))
    )

    session_lock = asyncio.Lock()

    # Run both tool calls concurrently
    res1, res2 = await asyncio.gather(
        _execute_tool_call(
            "bash",
            json.dumps({"command": "echo 'agy_done'"}),
            "call_1",
            chat.id,
            str(tmp_path),
            None,
            session,
            ws_manager,
            session_lock=session_lock,
        ),
        _execute_tool_call(
            "bash",
            json.dumps({"command": "echo 'codex_done'"}),
            "call_2",
            chat.id,
            str(tmp_path),
            None,
            session,
            ws_manager,
            session_lock=session_lock,
        ),
    )

    assert "agy_done" in res1
    assert "codex_done" in res2
    assert len(ws_broadcasts) >= 2
