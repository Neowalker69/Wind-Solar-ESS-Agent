"""用阿里百炼真实模型和 Station API 权威事实执行三类随机化 P2 Agent Loop。"""

import asyncio
import os


os.environ.setdefault("AGENT_HARNESS_MODEL_PROVIDER", "bailian")
os.environ.setdefault("VERIFY_MODEL_PROVIDER", "bailian")
os.environ.setdefault("VERIFY_MODEL_ID", os.getenv("BAILIAN_MODEL", "qwen3.7-plus"))

from apps.api_gateway.verify_p2_deepseek_e2e import main  # noqa: E402


if __name__ == "__main__":
    if not os.getenv("DASHSCOPE_API_KEY"):
        raise SystemExit("DASHSCOPE_API_KEY is required for real Bailian acceptance")
    asyncio.run(main())
