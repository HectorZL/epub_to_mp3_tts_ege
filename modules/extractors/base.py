from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

class BaseExtractor(ABC):
    """Base class for all text extractors"""
    
    @classmethod
    @abstractmethod
    def supports_file(cls, file_path: str) -> bool:
        """Check if this extractor supports the given file type"""
        pass
    
    @abstractmethod
    async def extract_text(self, file_path: str) -> str:
        """Extract text from the given file"""
        pass


extractors = {}

def register_extractor(extractor_class):
    """Decorator to register extractor classes"""
    extractors[extractor_class.__name__] = extractor_class
    return extractor_class


def get_extractor(file_path: str) -> Optional[BaseExtractor]:
    """Get the appropriate extractor for the given file"""
    for extractor_class in extractors.values():
        if extractor_class.supports_file(file_path):
            return extractor_class()
    return None
