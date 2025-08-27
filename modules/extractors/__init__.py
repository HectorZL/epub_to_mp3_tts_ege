from .base import BaseExtractor, get_extractor
from .pdf_extractor import PDFExtractor
from .epub_extractor import EPUBExtractor

# This will ensure the extractors are registered when the module is imported
__all__ = ['BaseExtractor', 'PDFExtractor', 'EPUBExtractor', 'get_extractor']
