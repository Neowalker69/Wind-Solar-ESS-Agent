from packages.model.config import load_model_config
from packages.model.router import ModelRouter


def main() -> None:
    config = load_model_config()
    router = ModelRouter.from_config(config)
    print(
        "model provider ready: "
        f"provider={config.provider} model={router.default_model_id}",
        flush=True,
    )


if __name__ == "__main__":
    main()
