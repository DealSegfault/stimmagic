from types import SimpleNamespace

import pytest

from agent.v2.service import _tool_scope_for_chat


@pytest.mark.parametrize("chat,skills,expected", [
    (None, None, "agent"),
    (SimpleNamespace(flow_id=None), ["video-assembly"], "agent"),
    (SimpleNamespace(flow_id=1), None, "flow"),
    (SimpleNamespace(flow_id=1), ["other-skill"], "flow"),
    (SimpleNamespace(flow_id=1), ["video-assembly"], "agent"),
])
def test_tool_scope_respects_flow_and_explicit_assembly(chat, skills, expected):
    assert _tool_scope_for_chat(chat, skills) == expected
