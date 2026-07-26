from types import SimpleNamespace

import pytest

from config import LLMEndpointConfig, LLMRoleConfig


def _stub_settings(*, role_models=None, **overrides):
    """A settings stub with the per-role model accessor the resolver needs.

    ``role_models`` maps a settings role to its saved slug; anything unset is
    ``auto`` (pick the best available model), which is the shipped default.
    """
    models = {
        "quick_task": "auto", "tool_assistant": "auto",
        "chat": "auto", "flow": "auto",
        **(role_models or {}),
    }
    defaults = dict(
        llm_providers=[],
        llm_reasoning_levels={},
        llm_model_prompts={},
        get_role_model_slug=lambda role, profile_id=None: models.get(role, "auto"),
        get_llm_role_config=lambda _role: LLMRoleConfig(source="auto"),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)



def test_retired_model_aliases_normalize_to_minimax(monkeypatch):
    import llm_resolver

    monkeypatch.setattr(
        "privacy_lockdown.is_privacy_lockdown_enabled",
        lambda: False,
    )

    assert llm_resolver.normalize_model_slug("agent-max") == "stimma:minimax-m3"
    assert llm_resolver.normalize_model_slug("default") == "stimma:minimax-m3"
    assert llm_resolver.normalize_model_slug("stimma:gpt-5.6-sol") == "stimma:gpt-5.6-sol"
    assert (
        llm_resolver.resolve_chat_model_slug("agent-max", None, "auto")
        == "stimma:minimax-m3"
    )


def test_config_migration_rewrites_retired_model_aliases(tmp_path):
    import yaml

    from config import _migrate_legacy_llm_model_slugs

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_model: agent-max\n"
        "quick_task_model: default\n"
        "llm_reasoning_levels:\n"
        "  agent-max: high\n"
        "  default: medium\n"
    )

    assert _migrate_legacy_llm_model_slugs(config_path) is True
    migrated = yaml.safe_load(config_path.read_text())

    assert migrated["default_model"] == "stimma:minimax-m3"
    assert migrated["quick_task_model"] == "stimma:minimax-m3"
    assert migrated["llm_reasoning_levels"] == {"stimma:minimax-m3": "high"}
    assert config_path.with_suffix(".yaml.bak").exists()
    assert _migrate_legacy_llm_model_slugs(config_path) is False


def test_global_model_settings_migrate_into_each_profile(tmp_path):
    """The two globals seed all four per-profile roles, then disappear.

    Quick tasks seeds both background roles and the chat default seeds chats —
    the closest reading of what each global meant. Flows had no predecessor.
    """
    import yaml

    from config import _migrate_global_models_to_profiles

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_model: stimma:claude-opus-5\n"
        "quick_task_model: stimma:claude-haiku-4.5\n"
        "profiles:\n"
        "  - id: default\n"
        "    name: Default\n"
        "  - id: work\n"
        "    name: Work\n"
        "    agent:\n"
        "      models:\n"
        "        chat: stimma:gpt-5.6-sol\n"
    )

    assert _migrate_global_models_to_profiles(config_path) is True
    migrated = yaml.safe_load(config_path.read_text())

    assert "default_model" not in migrated
    assert "quick_task_model" not in migrated

    default_models = migrated["profiles"][0]["agent"]["models"]
    assert default_models == {
        "quick_task": "stimma:claude-haiku-4.5",
        "tool_assistant": "stimma:claude-haiku-4.5",
        "chat": "stimma:claude-opus-5",
    }
    # `flow` is a new setting, not a renamed old one. Seeding it from the chat
    # default would put bulk flow work on the user's conversation model, which
    # is usually the priciest thing they have; it starts on `auto` instead.
    assert "flow" not in default_models

    # An explicit per-profile choice is never overwritten by the seed.
    assert migrated["profiles"][1]["agent"]["models"]["chat"] == "stimma:gpt-5.6-sol"

    # Idempotent: nothing left to migrate on a second pass.
    assert _migrate_global_models_to_profiles(config_path) is False


def test_migration_of_a_config_with_no_global_models_is_a_noop(tmp_path):
    from config import _migrate_global_models_to_profiles

    config_path = tmp_path / "config.yaml"
    config_path.write_text("profiles:\n  - id: default\n    name: Default\n")

    assert _migrate_global_models_to_profiles(config_path) is False


def test_chat_cloud_default_becomes_auto_in_privacy_lockdown(monkeypatch):
    import llm_resolver

    monkeypatch.setattr(
        "privacy_lockdown.is_privacy_lockdown_enabled",
        lambda: True,
    )

    assert llm_resolver.resolve_chat_model_slug(None, None, "agent-max") == "auto"
    assert llm_resolver.resolve_chat_model_slug("agent-max", None, "local") == "auto"
    assert llm_resolver.resolve_chat_model_slug(None, None, "local") == "local"


@pytest.mark.asyncio
async def test_chat_lockdown_cloud_default_resolves_to_local_endpoint(monkeypatch):
    import llm_resolver

    endpoint = LLMEndpointConfig(
        url="http://localhost:8000/v1",
        model="local-model",
    )
    settings = SimpleNamespace(
        get_llm_role_config=lambda _role: LLMRoleConfig(
            source="auto",
            endpoint=endpoint,
        ),
    )

    monkeypatch.setattr(
        "privacy_lockdown.is_privacy_lockdown_enabled",
        lambda: True,
    )
    monkeypatch.setattr(llm_resolver, "get_settings", lambda: settings)

    slug = llm_resolver.resolve_chat_model_slug(None, None, "agent-max")
    cfg = await llm_resolver.get_chat_llm_config(slug, role="agent")

    assert slug == "auto"
    assert cfg is endpoint


@pytest.mark.asyncio
async def test_chat_auto_uses_builtin_catalog_before_cloud_fetch(monkeypatch):
    """Before the live catalog is fetched, the built-in fallback is all `auto`
    has to choose from — so it lands on MiniMax rather than failing."""
    import llm_resolver

    seen = {}

    async def fake_cloud_config(role, *, model_slug=None, max_context_tokens=None, quick_task=False):
        seen["role"] = role
        seen["model_slug"] = model_slug
        seen["max_context_tokens"] = max_context_tokens
        return LLMEndpointConfig(
            url="https://cloud.example/api/llm/v1",
            model=role,
            max_context_tokens=max_context_tokens or 0,
        )

    async def cloud_available():
        return True

    monkeypatch.setattr(llm_resolver, "get_settings", lambda: _stub_settings())
    monkeypatch.setattr(llm_resolver, "_get_stimma_cloud_config", fake_cloud_config)
    monkeypatch.setattr(llm_resolver, "_cloud_is_available", cloud_available)
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    cfg = await llm_resolver.get_chat_llm_config("auto", role="chat")

    assert cfg.model == "stimma:minimax-m3"
    assert seen["model_slug"] == "stimma:minimax-m3"
    assert seen["max_context_tokens"] == llm_resolver.get_max_context_tokens(
        "stimma:minimax-m3"
    )


@pytest.mark.asyncio
async def test_auto_draws_the_whole_lineup_from_one_family(monkeypatch):
    """With the real cloud catalog loaded, `auto` picks a coherent set from the
    highest-ranked family rather than a per-role mix across vendors."""
    import llm_resolver

    monkeypatch.setattr(llm_resolver, "get_settings", lambda: _stub_settings())
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)
    llm_resolver.set_catalog_cache([
        {"slug": "stimma:claude-opus-5", "name": "Claude Opus 5", "model_vendor": "anthropic"},
        {"slug": "stimma:claude-sonnet-5", "name": "Claude Sonnet 5", "model_vendor": "anthropic"},
        {"slug": "stimma:claude-haiku-4.5", "name": "Claude Haiku 4.5", "model_vendor": "anthropic"},
        {"slug": "stimma:minimax-m3", "name": "MiniMax M3", "model_vendor": "minimax"},
        {"slug": "stimma:gpt-5.6-sol", "name": "GPT-5.6 Sol", "model_vendor": "openai"},
    ])
    try:
        candidates = llm_resolver.auto_candidates(cloud_available=True)
        from model_tiers import select_auto_models

        chosen = select_auto_models(candidates)
    finally:
        llm_resolver.set_catalog_cache([])

    assert chosen["chat"] == "stimma:claude-opus-5"
    assert chosen["tool_assistant"] == "stimma:claude-sonnet-5"
    assert chosen["flow"] == "stimma:claude-sonnet-5"
    assert chosen["quick_task"] == "stimma:claude-haiku-4.5"


@pytest.mark.asyncio
async def test_auto_excludes_cloud_models_when_signed_out(monkeypatch):
    """A signed-out install must not have `auto` pick a model it cannot call."""
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(llm_providers=[_local_provider()]),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    candidates = llm_resolver.auto_candidates(cloud_available=False)

    assert [c.slug for c in candidates] == ["local-abc123:qwen3-vl"]


@pytest.mark.asyncio
async def test_available_models_auto_describes_local_only_fallback(monkeypatch):
    from routes import models as models_route
    import firebase_auth

    endpoint = LLMEndpointConfig(
        url="http://localhost:8000/v1",
        model="local-model",
        max_context_tokens=64_000,
        input_modalities=["text", "image"],
        supports_tools=True,
    )
    settings = _stub_settings(
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llms={
            "agent": LLMRoleConfig(source="auto", endpoint=endpoint),
            "agent-fast": LLMRoleConfig(source="auto", endpoint=endpoint),
        },
    )

    async def no_cloud_token():
        return None

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", no_cloud_token)

    payload = await models_route.get_available_models()
    auto_model = payload["models"][0]
    local_model = next(model for model in payload["models"] if model["slug"] == "local")

    assert auto_model["available"] is True
    assert auto_model["resolved_slug"] == "local"
    assert auto_model["name"] == "Auto: local-model"
    assert auto_model["description"] == "Uses your configured model endpoint."
    assert auto_model["max_context_tokens"] == 64_000
    assert local_model["available"] is True
    assert local_model["input_modalities"] == ["text", "image"]
    assert local_model["supports_tools"] is True

    slugs = {model["slug"] for model in payload["models"]}
    assert "stimma:minimax-m3" not in slugs
    assert not {"gpt54", "kimi-k2", "opus", "sonnet"} & slugs


def test_legacy_endpoint_profile_persists_capabilities_for_both_roles(monkeypatch):
    from routes import settings as settings_route

    endpoint = LLMEndpointConfig(
        url="http://localhost:8000/v1",
        model="vision-model",
    )
    settings = SimpleNamespace(
        llms={
            "agent": LLMRoleConfig(source="auto", endpoint=endpoint),
            "agent-fast": LLMRoleConfig(source="auto", endpoint=endpoint),
        },
    )
    writes = []
    monkeypatch.setattr(settings_route, "get_settings", lambda: settings)
    monkeypatch.setattr(
        settings_route,
        "_update_llm_config",
        lambda role, data: writes.append((role, data)),
    )

    settings_route._persist_test_meta(
        True,
        {
            "vision": SimpleNamespace(passed=True),
            "tools": SimpleNamespace(passed=True),
        },
    )

    assert {role for role, _data in writes} == {"agent", "agent-fast"}
    assert all(
        data["endpoint"]["input_modalities"] == ["text", "image"]
        and data["endpoint"]["supports_tools"] is True
        for _role, data in writes
    )


@pytest.mark.asyncio
async def test_available_models_setup_state_is_not_a_hidden_model_list(monkeypatch):
    from routes import models as models_route
    import firebase_auth

    settings = _stub_settings(
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llms={
            "agent": LLMRoleConfig(source="auto"),
            "agent-fast": LLMRoleConfig(source="auto"),
        },
    )

    async def no_cloud_token():
        return None

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", no_cloud_token)

    payload = await models_route.get_available_models()
    auto_model = payload["models"][0]
    slugs = {model["slug"] for model in payload["models"]}

    assert auto_model["available"] is False
    assert auto_model["name"] == "Set up AI models"
    assert auto_model["description"] == "Add a model provider or sign in to your Stimma account."
    assert {"local", "auto"} == slugs


@pytest.mark.asyncio
async def test_available_models_lockdown_exposes_only_local_models(monkeypatch):
    from routes import models as models_route
    import firebase_auth

    endpoint = LLMEndpointConfig(
        url="http://localhost:8000/v1",
        model="local-model",
        max_context_tokens=64_000,
    )
    settings = _stub_settings(
        role_models={"chat": "agent-max"},
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llms={
            "agent": LLMRoleConfig(source="auto", endpoint=endpoint),
            "agent-fast": LLMRoleConfig(source="auto", endpoint=endpoint),
        },
    )

    async def cloud_auth_must_not_run():
        raise AssertionError("cloud auth was accessed during Privacy Lockdown")

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr(models_route, "is_privacy_lockdown_enabled", lambda: True)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", cloud_auth_must_not_run)

    payload = await models_route.get_available_models()

    assert {model["slug"] for model in payload["models"]} == {"auto", "local"}
    assert all(model["source"] != "stimma_cloud" for model in payload["models"])
    assert payload["models"][0]["resolved_slug"] == "local"
    assert payload["global_default"] == "auto"
    assert payload["cloud_status"] == "privacy_lockdown"
    assert payload["cloud_message"] == ""


@pytest.mark.asyncio
async def test_available_models_lockdown_setup_copy_is_local_only(monkeypatch):
    from routes import models as models_route
    import firebase_auth

    settings = _stub_settings(
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llms={
            "agent": LLMRoleConfig(source="auto"),
            "agent-fast": LLMRoleConfig(source="auto"),
        },
    )

    async def cloud_auth_must_not_run():
        raise AssertionError("cloud auth was accessed during Privacy Lockdown")

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr(models_route, "is_privacy_lockdown_enabled", lambda: True)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", cloud_auth_must_not_run)

    payload = await models_route.get_available_models()
    auto_model = payload["models"][0]

    assert auto_model["available"] is False
    assert auto_model["name"] == "Set up a local model"
    assert auto_model["description"] == "Add a model endpoint in Settings > Chat Models."
    assert {model["slug"] for model in payload["models"]} == {"auto", "local"}


@pytest.mark.asyncio
async def test_available_models_acceptance_provider_advertises_auto(monkeypatch):
    """The acceptance lane serves a deterministic in-process LLM for every
    role, so the picker must report `auto` as available. Otherwise the chat
    composer treats the model as unavailable and silently no-ops sends."""
    from routes import models as models_route
    import firebase_auth

    settings = _stub_settings(
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llms={
            "agent": LLMRoleConfig(source="auto"),
            "agent-fast": LLMRoleConfig(source="auto"),
        },
    )

    async def no_cloud_token():
        return None

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", no_cloud_token)
    monkeypatch.setenv("STIMMA_TEST_PROVIDER", "1")

    payload = await models_route.get_available_models()
    auto_model = payload["models"][0]

    assert auto_model["slug"] == "auto"
    assert auto_model["available"] is True
    assert auto_model["resolved_slug"] == "auto"
    assert payload["cloud_status"] == "available"


def _local_provider(**overrides):
    from config import LLMProviderConfig, LLMProviderModelConfig

    provider = LLMProviderConfig(
        id="local-abc123",
        kind="local",
        name="my-llm-box",
        base_url="http://llmbox.local:8080/v1",
        models=[
            LLMProviderModelConfig(
                id="local-abc123:qwen3-vl",
                model_id="qwen3-vl",
                name="Qwen3 VL",
                max_context_tokens=32_000,
            )
        ],
    )
    for key, value in overrides.items():
        setattr(provider, key, value)
    return provider


def _fast_provider():
    """A second local provider whose model is small enough to read as `fast`."""
    from config import LLMProviderConfig, LLMProviderModelConfig

    return LLMProviderConfig(
        id="local-fast",
        kind="local",
        name="little-box",
        base_url="http://little.local:8080/v1",
        models=[LLMProviderModelConfig(
            id="local-fast:tiny-3b",
            model_id="tiny-3b",
            name="Tiny 3B",
            model_vendor="alibaba",
        )],
    )


@pytest.mark.asyncio
async def test_quick_task_falls_back_to_only_provider_model(monkeypatch):
    """A saved cloud quick-task model with no cloud auth must fall back to the
    one configured provider model instead of demanding a sign-in."""
    import llm_resolver

    settings = _stub_settings(
        role_models={"quick_task": "stimma:minimax-m3", "chat": "stimma:minimax-m3"},
        llm_providers=[_local_provider()],
    )

    async def no_cloud(*args, **kwargs):
        return None

    async def no_token():
        return None

    monkeypatch.setattr(llm_resolver, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_resolver, "_get_stimma_cloud_config", no_cloud)
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)
    monkeypatch.setattr("auth_storage.load_auth_state", lambda: None)
    monkeypatch.setattr("firebase_auth.get_valid_id_token", no_token)

    cfg = await llm_resolver.get_effective_llm_config("agent-fast")

    assert cfg.model == "qwen3-vl"
    assert cfg.url == "http://llmbox.local:8080/v1"


@pytest.mark.asyncio
async def test_quick_task_fallback_skips_unusable_providers(monkeypatch):
    """Disabled/broken providers are not fallback candidates."""
    import llm_resolver
    from llm_resolver import LLMUnavailableError

    settings = _stub_settings(
        role_models={"quick_task": "stimma:minimax-m3", "chat": "stimma:minimax-m3"},
        llm_providers=[
            _local_provider(enabled=False),
            _local_provider(last_test_passed=False),
        ],
    )

    async def no_cloud(*args, **kwargs):
        return None

    async def no_token():
        return None

    monkeypatch.setattr(llm_resolver, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_resolver, "_get_stimma_cloud_config", no_cloud)
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)
    monkeypatch.setattr("auth_storage.load_auth_state", lambda: None)
    monkeypatch.setattr("firebase_auth.get_valid_id_token", no_token)

    with pytest.raises(LLMUnavailableError):
        await llm_resolver.get_effective_llm_config("agent-fast")


@pytest.mark.asyncio
async def test_chat_auto_falls_back_to_provider_model(monkeypatch):
    """'auto' with no cloud auth and no legacy endpoint resolves to the
    configured provider model."""
    import llm_resolver

    settings = _stub_settings(llm_providers=[_local_provider()])

    async def no_cloud(*args, **kwargs):
        return None

    monkeypatch.setattr(llm_resolver, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_resolver, "_get_stimma_cloud_config", no_cloud)
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    cfg = await llm_resolver.get_chat_llm_config("auto", role="agent")

    assert cfg.model == "qwen3-vl"
    assert cfg.url == "http://llmbox.local:8080/v1"


@pytest.mark.asyncio
async def test_available_models_auto_and_quick_task_resolve_to_provider_model(monkeypatch):
    """/models/available mirrors the resolver fallback: 'auto' resolves to the
    one provider model and quick_task_model reports the model in effect."""
    from routes import models as models_route
    import firebase_auth

    settings = _stub_settings(
        role_models={"quick_task": "stimma:minimax-m3"},
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llm_providers=[_local_provider()],
        llms={
            "agent": LLMRoleConfig(source="auto"),
            "agent-fast": LLMRoleConfig(source="auto"),
        },
    )

    async def no_cloud_token():
        return None

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    # The route asks the resolver what each role lands on, and the resolver
    # reads settings itself — both must see the same install.
    monkeypatch.setattr("llm_resolver.get_settings", lambda: settings)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", no_cloud_token)

    payload = await models_route.get_available_models()
    auto_model = payload["models"][0]

    assert auto_model["available"] is True
    assert auto_model["resolved_slug"] == "local-abc123:qwen3-vl"
    assert auto_model["name"] == "Auto: Qwen3 VL"
    # The saved cloud slug is still what's stored, but with no cloud auth it
    # can't be called — `resolved` reports the model that actually will be, so
    # the settings UI never shows a dead selection.
    assert payload["role_defaults"]["quick_task"]["profile"] == "stimma:minimax-m3"
    assert payload["role_defaults"]["quick_task"]["resolved"] == "local-abc123:qwen3-vl"
    assert payload["role_defaults"]["chat"]["resolved"] == "local-abc123:qwen3-vl"


@pytest.mark.asyncio
async def test_project_override_beats_the_profile_setting(monkeypatch):
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(
            role_models={"tool_assistant": "local-abc123:qwen3-vl"},
            llm_providers=[_local_provider()],
        ),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    async def project_says(role, project_id):
        return "local-abc123:qwen3-vl" if role == "tool_assistant" else None

    # An explicit project override wins outright...
    slug = await llm_resolver.resolve_role_model_slug(
        "tool_assistant", project_slug="local-abc123:qwen3-vl",
    )
    assert slug == "local-abc123:qwen3-vl"

    # ...and with no override the profile setting stands.
    assert await llm_resolver.resolve_role_model_slug("tool_assistant") == (
        "local-abc123:qwen3-vl"
    )


@pytest.mark.asyncio
async def test_unreachable_saved_slug_resolves_to_an_available_model(monkeypatch):
    """A cloud model saved while signed in must not be reported as in effect
    after signing out — the UI would show a selection nothing can honor."""
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(
            role_models={"chat": "stimma:claude-opus-5"},
            llm_providers=[_local_provider()],
        ),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    async def no_cloud():
        return False

    monkeypatch.setattr(llm_resolver, "_cloud_is_available", no_cloud)

    assert await llm_resolver.resolve_role_model_slug("chat") == "local-abc123:qwen3-vl"


@pytest.mark.asyncio
async def test_saved_slug_survives_when_there_is_nothing_to_switch_to(monkeypatch):
    """With no candidates at all (legacy endpoint pair only), the saved
    selection is left alone rather than rewritten to a model that doesn't exist."""
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(role_models={"chat": "stimma:claude-opus-5"}),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    async def no_cloud():
        return False

    monkeypatch.setattr(llm_resolver, "_cloud_is_available", no_cloud)

    assert await llm_resolver.resolve_role_model_slug("chat") == "stimma:claude-opus-5"


@pytest.mark.asyncio
async def test_privacy_lockdown_keeps_auto_off_the_cloud(monkeypatch):
    """Lockdown is the sharpest case for `auto`: it must never surface a hosted
    model, even one the account is signed in for."""
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(llm_providers=[_local_provider()]),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: True)

    llm_resolver.set_catalog_cache([
        {"slug": "stimma:claude-opus-5", "name": "Claude Opus 5",
         "model_vendor": "anthropic"},
    ])
    try:
        # Even told cloud is available, lockdown drops every hosted candidate.
        candidates = llm_resolver.auto_candidates(cloud_available=True)
    finally:
        llm_resolver.set_catalog_cache([])

    assert [c.slug for c in candidates] == ["local-abc123:qwen3-vl"]


@pytest.mark.asyncio
async def test_remote_providers_are_dropped_in_lockdown(monkeypatch):
    """A bring-your-own OpenAI key is still an egress path; lockdown excludes it
    while leaving local servers selectable."""
    import llm_resolver
    from config import LLMProviderConfig, LLMProviderModelConfig

    remote = LLMProviderConfig(
        id="openai-1", kind="openai", name="OpenAI",
        base_url="https://api.openai.com/v1",
        models=[LLMProviderModelConfig(
            id="openai-1:gpt-5.6-sol", model_id="gpt-5.6-sol",
            name="GPT-5.6 Sol", model_vendor="openai",
        )],
    )
    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(llm_providers=[remote, _local_provider()]),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: True)

    candidates = llm_resolver.auto_candidates(cloud_available=False)

    assert [c.slug for c in candidates] == ["local-abc123:qwen3-vl"]


@pytest.mark.asyncio
async def test_role_defaults_describe_the_fallback_options_not_the_selection(monkeypatch):
    """The picker labels its Automatic / Inherit rows from `auto` and
    `profile_resolved`. Both must describe what choosing that row would GIVE
    you, independent of what is currently saved — labelling them from the
    active selection makes the row claim it would keep the current model."""
    from routes import models as models_route
    import firebase_auth

    settings = _stub_settings(
        # Explicitly pinned to a mid-tier model, so `auto` must differ.
        role_models={"quick_task": "local-abc123:qwen3-vl"},
        cloud=SimpleNamespace(base_url="https://cloud.example"),
        llm_providers=[_local_provider(), _fast_provider()],
        llms={
            "agent": LLMRoleConfig(source="auto"),
            "agent-fast": LLMRoleConfig(source="auto"),
        },
    )

    async def no_cloud_token():
        return None

    monkeypatch.setattr(models_route, "get_settings", lambda: settings)
    monkeypatch.setattr("llm_resolver.get_settings", lambda: settings)
    monkeypatch.setattr(firebase_auth, "get_valid_id_token", no_cloud_token)

    entry = (await models_route.get_available_models())["role_defaults"]["quick_task"]

    assert entry["profile"] == "local-abc123:qwen3-vl"
    # `auto` ignores the pin and reports the tier-matched model for the role.
    assert entry["auto"] == "local-fast:tiny-3b"
    # `profile_resolved` is what a project inheriting would land on.
    assert entry["profile_resolved"] == "local-abc123:qwen3-vl"


@pytest.mark.asyncio
async def test_cold_catalog_does_not_downgrade_a_saved_cloud_model(monkeypatch):
    """Right after startup the live catalog hasn't been fetched, so the only
    cloud models we know of are the compiled-in fallbacks. Absence from that
    list says nothing about whether a saved cloud slug is reachable — treating
    it as unreachable would silently move every caption and flow step off the
    user's chosen model until something happened to fetch the catalog."""
    import llm_resolver

    monkeypatch.setattr(
        llm_resolver, "get_settings",
        lambda: _stub_settings(
            role_models={"chat": "stimma:claude-opus-5"},
            llm_providers=[_local_provider()],
        ),
    )
    monkeypatch.setattr("privacy_lockdown.is_privacy_lockdown_enabled", lambda: False)

    async def cloud_up():
        return True

    monkeypatch.setattr(llm_resolver, "_cloud_is_available", cloud_up)
    llm_resolver.set_catalog_cache([])  # cold

    assert await llm_resolver.resolve_role_model_slug("chat") == "stimma:claude-opus-5"

    # Once the catalog IS known and the model genuinely isn't in it, the
    # downgrade is correct again.
    llm_resolver.set_catalog_cache([
        {"slug": "stimma:minimax-m3", "name": "MiniMax M3", "model_vendor": "minimax"},
    ])
    try:
        assert await llm_resolver.resolve_role_model_slug("chat") != "stimma:claude-opus-5"
    finally:
        llm_resolver.set_catalog_cache([])
