import random
import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def with_backoff(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 12.0,
    retryable: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except retryable as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            delay = min(base_delay_seconds * (2**attempt), max_delay_seconds)
            time.sleep(delay + random.uniform(0, 0.25))
    assert last_error is not None
    raise last_error
