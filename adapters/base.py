from __future__ import annotations
from abc import ABC, abstractmethod

class Adapter(ABC):
    @abstractmethod
    def run(self) -> None:
        """Bloquea y procesa eventos continuamente."""
        raise NotImplementedError