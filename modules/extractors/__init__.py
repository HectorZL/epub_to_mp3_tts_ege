from typing import Dict, Type, Optional, List
import os
from .base import BaseExtractor
from .pdf_extractor import PDFExtractor
from .epub_extractor import EPUBExtractor

# Register extractors
EXTRACTORS: List[Type[BaseExtractor]] = [
    PDFExtractor,
    EPUBExtractor
]

def get_extractor(file_path: str) -> Optional[BaseExtractor]:
    """Get the appropriate extractor for the given file"""
    for extractor_cls in EXTRACTORS:
        if extractor_cls.supports_file(file_path):
            return extractor_cls()
    return None

__all__ = ['BaseExtractor', 'PDFExtractor', 'EPUBExtractor', 'get_extractor']
