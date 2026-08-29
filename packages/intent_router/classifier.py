from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifierResult:
    label: str
    confidence: float
    safety_flags: list[str]


class DeterministicClassifier:
    def classify(self, text: str) -> ClassifierResult:
        if "改" in text and ("代码" in text or "交互" in text or "图表" in text):
            return ClassifierResult("code.change", 0.9, [])
        if "无意义" in text or text.strip() in {"哈哈", "呵呵"}:
            return ClassifierResult("chat.noise", 0.88, [])
        if "安全违规" in text:
            return ClassifierResult("safety.violation", 0.91, ["policy_marker"])
        return ClassifierResult("unknown", 0.1, [])
