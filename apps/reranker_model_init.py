from __future__ import annotations

import os
from pathlib import Path


DEFAULT_MODELSCOPE_MODEL = "AI-ModelScope/bge-reranker-v2-m3"
DEFAULT_TARGET = "/models/bge-reranker-v2-m3"


def model_is_complete(target: Path) -> bool:
    return (
        (target / "config.json").is_file()
        and (target / "tokenizer.json").is_file()
        and any(target.glob("*.safetensors"))
    )


def main() -> None:
    from modelscope.hub.snapshot_download import snapshot_download

    model_id = os.getenv("MODELSCOPE_MODEL_ID", DEFAULT_MODELSCOPE_MODEL)
    target = Path(os.getenv("MODEL_TARGET_DIR", DEFAULT_TARGET))
    if model_is_complete(target):
        print(f"ModelScope model already present: {target}")
        return
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        model_id=model_id,
        revision=os.getenv("MODELSCOPE_MODEL_REVISION", "master"),
        local_dir=str(target),
        max_workers=max(1, int(os.getenv("MODELSCOPE_DOWNLOAD_WORKERS", "4"))),
    )
    if not model_is_complete(target):
        raise RuntimeError("modelscope_reranker_download_incomplete")
    print(f"Downloaded {model_id} from ModelScope to {target}")


if __name__ == "__main__":
    main()
