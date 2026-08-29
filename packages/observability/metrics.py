from collections import Counter


class Metrics:
    def __init__(self) -> None:
        self.counters: Counter[tuple[str, tuple[str, ...]]] = Counter()

    def inc(self, name: str, labels: tuple[str, ...] = ()) -> None:
        self.counters[(name, labels)] += 1

    def render_prometheus(self) -> str:
        lines = []
        for (name, label_values), value in sorted(self.counters.items()):
            if label_values:
                label_text = ",".join(f'label_{index}="{label}"' for index, label in enumerate(label_values))
                lines.append(f"{name}{{{label_text}}} {value}")
            else:
                lines.append(f"{name} {value}")
        return "\n".join(lines) + ("\n" if lines else "")


GLOBAL_METRICS = Metrics()
