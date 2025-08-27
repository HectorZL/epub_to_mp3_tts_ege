import ebooklib
from ebooklib import epub
from typing import List

from .base import BaseExtractor, register_extractor

@register_extractor
class EPUBExtractor(BaseExtractor):
    """Extractor for EPUB files"""
    
    @classmethod
    def supports_file(cls, file_path: str) -> bool:
        """Check if the file is an EPUB"""
        return str(file_path).lower().endswith('.epub')
    
    async def extract_text(self, file_path: str) -> str:
        """Extract text from an EPUB file"""
        try:
            book = epub.read_epub(file_path)
            return self._extract_chapters(book)
        except Exception as e:
            raise Exception(f"Error extracting text from EPUB: {str(e)}")
    
    def _extract_chapters(self, book) -> str:
        """Extract text from all chapters in the book"""
        chapters = []
        
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                try:
                    # Convert bytes to string if necessary
                    content = item.get_content()
                    if isinstance(content, bytes):
                        content = content.decode('utf-8', errors='ignore')
                    
                    # Basic HTML/XML tag stripping (simplified)
                    text = self._strip_tags(content)
                    if text.strip():
                        chapters.append(text)
                except Exception as e:
                    print(f"Warning: Could not process item: {str(e)}")
                    continue
        
        return '\n\n'.join(chapters)
    
    @staticmethod
    def _strip_tags(html: str) -> str:
        """Basic HTML/XML tag stripper"""
        if not html:
            return ""
            
        # Remove script and style elements
        import re
        clean = re.compile(r'<(script|style).*?>.*?</\1>', re.DOTALL)
        text = re.sub(clean, '', html)
        
        # Remove all other tags
        clean = re.compile(r'<[^>]+>')
        text = re.sub(clean, '', text)
        
        # Decode HTML entities
        import html
        text = html.unescape(text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text
