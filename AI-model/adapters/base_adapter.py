from abc import ABC, abstractmethod

from dataset import CaseSequence


class BaseCaseAdapter(ABC):
    @abstractmethod
    def load_cases(self) -> list[CaseSequence]:
        """Load normalized, ordered case sequences."""
        raise NotImplementedError
