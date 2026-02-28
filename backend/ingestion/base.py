from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List
from datetime import datetime


@dataclass
class Chunk:
    text: str
    source_type: str       # "text" | "pdf" | "csv" | "code" | "chat" | "github"
    source_name: str       # filename or repo URL
    metadata: dict = field(default_factory=dict)


class BaseIngester(ABC):
    @abstractmethod
    def ingest(self, source_path: str) -> List[Chunk]:
        """Ingest a source and return a list of chunks."""
        pass

    def _get_timestamp(self) -> str:
        return datetime.utcnow().isoformat()
