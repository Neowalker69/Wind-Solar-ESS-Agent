from packages.model.adapters import BailianAdapter, DeepSeekAdapter
from packages.model.config import ModelProviderConfig, load_model_config
from packages.model.port import ModelPort


class ModelRouter:
    def __init__(self, default_model_id: str) -> None:
        self._adapters: dict[str, ModelPort] = {}
        self.default_model_id = default_model_id

    def register(self, adapter: ModelPort) -> None:
        self._adapters[adapter.model_id] = adapter

    def resolve(self, model_id: str | None = None) -> ModelPort:
        selected = model_id or self.default_model_id
        if selected not in self._adapters:
            raise KeyError("model_unavailable")
        return self._adapters[selected]

    @classmethod
    def from_config(cls, config: ModelProviderConfig | None = None) -> "ModelRouter":
        provider_config = config or load_model_config()
        if provider_config.provider == "deepseek":
            if not provider_config.deepseek.api_key:
                raise RuntimeError("model_provider_api_key_missing:deepseek")
            adapter = DeepSeekAdapter(
                api_key=provider_config.deepseek.api_key,
                base_url=provider_config.deepseek.base_url,
                model=provider_config.deepseek.model,
                thinking=provider_config.deepseek.thinking,
                reasoning_effort=provider_config.deepseek.reasoning_effort,
            )
        elif provider_config.provider == "bailian":
            if not provider_config.bailian.api_key:
                raise RuntimeError("model_provider_api_key_missing:bailian")
            adapter = BailianAdapter(
                api_key=provider_config.bailian.api_key,
                base_url=provider_config.bailian.base_url,
                model=provider_config.bailian.model,
            )
        else:
            raise RuntimeError(
                f"model_provider_unsupported:{provider_config.provider};"
                "supported=deepseek,bailian"
            )
        router = cls(default_model_id=adapter.model_id)
        router.register(adapter)
        return router
