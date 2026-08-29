import json
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_BAILIAN_MODEL = "qwen3.7-plus"
SUPPORTED_MODEL_PROVIDERS = frozenset({"deepseek", "bailian"})


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str | None = None
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    thinking: str | None = "disabled"
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class BailianConfig:
    api_key: str | None = None
    base_url: str = DEFAULT_BAILIAN_BASE_URL
    model: str = DEFAULT_BAILIAN_MODEL


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str
    deepseek: DeepSeekConfig = DeepSeekConfig()
    bailian: BailianConfig = BailianConfig()


def default_config_path() -> Path:
    return Path(os.getenv("AGENT_HARNESS_CONFIG", "~/.agent-harness/config.json")).expanduser()


def load_model_config(path: Path | None = None) -> ModelProviderConfig:
    config_path = path or default_config_path()
    data = _read_json(config_path)
    provider = str(
        os.getenv("AGENT_HARNESS_MODEL_PROVIDER")
        or data.get("model_provider")
        or data.get("provider")
        or ""
    ).strip().lower()
    if not provider:
        raise RuntimeError(
            "model_provider_required:set AGENT_HARNESS_MODEL_PROVIDER="
            "deepseek or bailian"
        )
    if provider not in SUPPORTED_MODEL_PROVIDERS:
        raise RuntimeError(
            f"model_provider_unsupported:{provider};supported=deepseek,bailian"
        )
    deepseek_data = data.get("deepseek", {})
    deepseek = DeepSeekConfig(
        api_key=_read_secret_environment("DEEPSEEK_API_KEY")
        or deepseek_data.get("api_key"),
        base_url=_normalize_deepseek_base_url(os.getenv("DEEPSEEK_BASE_URL") or deepseek_data.get("base_url") or DEFAULT_DEEPSEEK_BASE_URL),
        model=os.getenv("DEEPSEEK_MODEL") or deepseek_data.get("model") or DEFAULT_DEEPSEEK_MODEL,
        thinking=os.getenv("DEEPSEEK_THINKING") or deepseek_data.get("thinking") or "disabled",
        reasoning_effort=os.getenv("DEEPSEEK_REASONING_EFFORT") or deepseek_data.get("reasoning_effort"),
    )
    bailian_data = data.get("bailian", {})
    bailian = BailianConfig(
        api_key=_read_secret_environment("DASHSCOPE_API_KEY", "BAILIAN_API_KEY")
        or bailian_data.get("api_key"),
        base_url=(os.getenv("BAILIAN_BASE_URL") or bailian_data.get("base_url") or DEFAULT_BAILIAN_BASE_URL).rstrip("/"),
        model=os.getenv("BAILIAN_MODEL") or bailian_data.get("model") or DEFAULT_BAILIAN_MODEL,
    )
    return ModelProviderConfig(provider=provider, deepseek=deepseek, bailian=bailian)


def save_deepseek_api_key(api_key: str, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    data = _read_json(config_path)
    deepseek = data.setdefault("deepseek", {})
    deepseek["api_key"] = api_key
    deepseek.setdefault("base_url", DEFAULT_DEEPSEEK_BASE_URL)
    deepseek.setdefault("model", DEFAULT_DEEPSEEK_MODEL)
    deepseek.setdefault("thinking", "disabled")
    data["model_provider"] = "deepseek"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(0o600)
    return config_path


def save_bailian_api_key(api_key: str, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    data = _read_json(config_path)
    bailian = data.setdefault("bailian", {})
    bailian["api_key"] = api_key
    bailian.setdefault("base_url", DEFAULT_BAILIAN_BASE_URL)
    bailian.setdefault("model", DEFAULT_BAILIAN_MODEL)
    data["model_provider"] = "bailian"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(0o600)
    return config_path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid Agent Harness config: {path}") from exc


def _read_secret_environment(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    for key in keys:
        secret_path = os.getenv(f"{key}_FILE", "").strip()
        if not secret_path:
            continue
        path = Path(secret_path)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"model_provider_secret_file_unreadable:{key}") from exc
        if not value:
            raise RuntimeError(f"model_provider_secret_file_empty:{key}")
        return value
    return None


def _normalize_deepseek_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized.removesuffix("/v1")
    return normalized
