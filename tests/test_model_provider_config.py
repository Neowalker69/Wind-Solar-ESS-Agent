from pathlib import Path

import pytest

from packages.model.config import load_model_config
from packages.model.router import ModelRouter


def _isolated_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENT_HARNESS_CONFIG", str(tmp_path / "missing.json"))
    for key in (
        "AGENT_HARNESS_MODEL_PROVIDER",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEY_FILE",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_API_KEY_FILE",
        "BAILIAN_API_KEY",
        "BAILIAN_API_KEY_FILE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_provider_is_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolated_config(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="model_provider_required"):
        load_model_config()


def test_mock_provider_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolated_config(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_HARNESS_MODEL_PROVIDER", "mock")

    with pytest.raises(RuntimeError, match="model_provider_unsupported:mock"):
        load_model_config()


def test_deepseek_provider_builds_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolated_config(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_HARNESS_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test-model")

    config = load_model_config()
    router = ModelRouter.from_config(config)

    assert config.provider == "deepseek"
    assert router.resolve().provider == "deepseek"
    assert router.default_model_id == "deepseek-test-model"


def test_bailian_provider_reads_secret_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolated_config(monkeypatch, tmp_path)
    secret_file = tmp_path / "bailian-key"
    secret_file.write_text("test-only-key\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_HARNESS_MODEL_PROVIDER", "bailian")
    monkeypatch.setenv("DASHSCOPE_API_KEY_FILE", str(secret_file))
    monkeypatch.setenv("BAILIAN_MODEL", "qwen-test-model")

    config = load_model_config()
    router = ModelRouter.from_config(config)

    assert config.provider == "bailian"
    assert router.resolve().provider == "bailian"
    assert router.default_model_id == "qwen-test-model"
