
from queue import Queue
import threading
from typing import Any


class ThreadSafeQueue:
    def __init__(self):
        self._queue = Queue()
        self._lock = threading.Lock()
    
    def put(self, item: Any) -> None:
        """Dodaje element do kolejki w sposób bezpieczny dla wątków."""
        with self._lock:
            self._queue.put(item)

    def get(self) -> Any:
        """Pobiera element z kolejki w sposób bezpieczny dla wątków."""
        with self._lock:
            return self._queue.get_nowait()

    def empty(self) -> bool:
        """Sprawdza, czy kolejka jest pusta."""
        with self._lock:
            return self._queue.empty()