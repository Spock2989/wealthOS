
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, content: bytes, filename: str) -> bool:
        pass
    @abstractmethod
    def parse(self, content: bytes) -> List[Dict[str, Any]]:
        pass

class ParserRegistry:
    def __init__(self):
        self._parsers = []
    def register(self, parser: BaseParser):
        self._parsers.append(parser)
    def get_parser(self, content: bytes, filename: str) -> BaseParser:
        for p in self._parsers:
            if p.can_parse(content, filename):
                return p
        raise ValueError(f"No parser found for {filename}")
