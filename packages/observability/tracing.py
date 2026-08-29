from contextlib import contextmanager
from time import perf_counter


@contextmanager
def span(name: str):
    started = perf_counter()
    yield {"name": name, "duration_ms": lambda: int((perf_counter() - started) * 1000)}
