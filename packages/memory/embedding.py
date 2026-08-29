from __future__ import annotations

from hashlib import sha256
import math
import re
from typing import Protocol


class MemoryEncoder(Protocol):
    dimensions: int

    def encode(self, text: str) -> list[float]: ...


class HashingMemoryEncoder:
    """无需下载模型的确定性 1024 维编码器，后续可替换为领域模型。"""

    dimensions = 1024

    def encode(self, text: str) -> list[float]:
        normalized = text.strip().lower()
        words = re.findall(r"[a-z0-9_.:-]+", normalized)
        cjk = re.findall(r"[\u3400-\u9fff]", normalized)
        tokens = words + cjk + ["".join(cjk[index : index + 2]) for index in range(len(cjk) - 1)]
        vector = [0.0] * self.dimensions
        for token in tokens or [normalized or "empty"]:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector
