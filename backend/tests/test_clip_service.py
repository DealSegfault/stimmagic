from types import SimpleNamespace


def test_clip_uses_cpu_by_default_on_macos(monkeypatch):
    import clip_service

    ort = SimpleNamespace(
        get_available_providers=lambda: [
            "CoreMLExecutionProvider",
            "AzureExecutionProvider",
            "CPUExecutionProvider",
        ]
    )
    monkeypatch.setattr(clip_service.sys, "platform", "darwin")
    monkeypatch.delenv("STIMMA_CLIP_USE_COREML", raising=False)

    assert clip_service._get_clip_execution_providers(ort) == [
        "CPUExecutionProvider"
    ]


def test_clip_coreml_can_be_enabled_for_benchmarking(monkeypatch):
    import clip_service

    available = [
        "CoreMLExecutionProvider",
        "AzureExecutionProvider",
        "CPUExecutionProvider",
    ]
    ort = SimpleNamespace(get_available_providers=lambda: available)
    monkeypatch.setattr(clip_service.sys, "platform", "darwin")
    monkeypatch.setenv("STIMMA_CLIP_USE_COREML", "1")

    assert clip_service._get_clip_execution_providers(ort) == available
