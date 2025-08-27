import PyPDF2
from pathlib import Path
from typing import Optional

from .base import BaseExtractor, register_extractor

@register_extractor
class PDFExtractor(BaseExtractor):
    """Extractor for PDF files"""
    
    @classmethod
    def supports_file(cls, file_path: str) -> bool:
        """Check if the file is a PDF"""
        return str(file_path).lower().endswith('.pdf')
    
    async def extract_text(self, file_path: str) -> str:
        """Extract text from a PDF file"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
                return '\n'.join(text)
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")
