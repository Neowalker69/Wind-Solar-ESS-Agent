"""由 Proto 生成的 Agent Runtime 传输模块。"""

import sys

from . import agent_runtime as _agent_runtime

sys.modules.setdefault("agent_runtime", _agent_runtime)
