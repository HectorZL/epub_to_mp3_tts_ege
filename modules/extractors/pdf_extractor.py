import re
import PyPDF2
from typing import List, Optional, Tuple, Dict, Any
import asyncio

from .base import BaseExtractor

class PDFExtractor(BaseExtractor):
    """Extracts text from PDF files with chapter support"""
    
    # Common chapter patterns in PDFs
    CHAPTER_PATTERNS = [
        r'^\s*chapter\s+\d+',  # Chapter 1, Chapter 2, etc.
        r'^\s*\d+\s*$',         # Just a number on a line
        r'^\s*[IVXLCDM]+\s*$',  # Roman numerals
        r'^\s*[A-Z][A-Z\s]+$',  # All caps lines (often chapter titles)
        r'^\s*cap[ií]tulo\s+\d+',  # Capítulo 1, Capítulo 2, etc.
        r'^\s*parte\s+[IVXLCDM]+',  # Parte I, Parte II, etc.
        r'^\s*secci[oó]n\s+\d+',  # Sección 1, Sección 2, etc.
    ]
    
    def __init__(self):
        self.chapter_titles: List[str] = []
        self.chapter_pages: List[int] = []
        self.page_texts: List[str] = []
    
    async def extract_text(self, file_path: str) -> str:
        """Extract all text from the PDF"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text_parts = []
                
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                
                return '\n\n'.join(text_parts)
                
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")
    
    async def get_chapters(self, file_path: str) -> List[str]:
        """Extract chapter information from the PDF"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                self.chapter_titles = []
                self.chapter_pages = []
                self.page_texts = []
                
                # First, extract all page texts
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    self.page_texts.append(page_text)
                
                # Look for chapter titles in each page
                for i, page_text in enumerate(self.page_texts):
                    if not page_text.strip():
                        continue
                        
                    # Split into lines and clean them up
                    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    if not lines:
                        continue
                    
                    # Check first few lines for chapter titles
                    for line in lines[:5]:
                        if self._is_chapter_title(line):
                            self.chapter_titles.append(line)
                            self.chapter_pages.append(i)
                            break
                    
                    # Also check for common chapter patterns in the page text
                    for pattern in self.CHAPTER_PATTERNS:
                        matches = re.finditer(pattern, page_text, re.IGNORECASE | re.MULTILINE)
                        for match in matches:
                            line = match.group(0).strip()
                            if line and line not in self.chapter_titles:
                                self.chapter_titles.append(line)
                                self.chapter_pages.append(i)
                
                # If we found chapters, return them
                if self.chapter_titles:
                    return self.chapter_titles
                
                # Fallback: treat each page as a chapter
                return [f"Página {i+1}" for i in range(len(self.page_texts))]
                
        except Exception as e:
            print(f"Error getting chapters: {str(e)}")
            # Fallback: treat each page as a chapter
            return [f"Página {i+1}" for i in range(len(reader.pages))] if 'reader' in locals() else ["Documento completo"]
    
    async def extract_chapter(self, file_path: str, chapter_index: int) -> str:
        """Extract text for a specific chapter"""
        try:
            # If we haven't found chapters yet, get them now
            if not self.chapter_titles:
                await self.get_chapters(file_path)
            
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text_parts = []
                
                if not self.chapter_titles:
                    # If still no chapters, treat each page as a chapter
                    if 0 <= chapter_index < len(reader.pages):
                        page = reader.pages[chapter_index]
                        return page.extract_text() or ""
                    return ""
                
                # Get start and end pages for the chapter
                start_page = self.chapter_pages[chapter_index]
                if chapter_index + 1 < len(self.chapter_pages):
                    end_page = self.chapter_pages[chapter_index + 1]
                else:
                    end_page = len(reader.pages)
                
                # Extract text for the chapter
                for i in range(start_page, end_page):
                    page = reader.pages[i]
                    page_text = page.extract_text()
                    if page_text:
                        # For the first page, only include text after the chapter title
                        if i == start_page:
                            lines = page_text.split('\n')
                            for j, line in enumerate(lines):
                                if line.strip() == self.chapter_titles[chapter_index].strip():
                                    page_text = '\n'.join(lines[j+1:])
                                    break
                        text_parts.append(page_text)
                
                return '\n\n'.join(text_parts)
                
        except Exception as e:
            raise Exception(f"Error extracting chapter {chapter_index}: {str(e)}")
    
    def _is_chapter_title(self, text: str) -> bool:
        """Check if a line of text looks like a chapter title"""
        if not text or len(text) > 100:  # Too long to be a chapter title
            return False
            
        text_lower = text.lower()
        
        # Check against common chapter patterns
        for pattern in self.CHAPTER_PATTERNS:
            if re.match(pattern, text_lower, re.IGNORECASE):
                return True
        
        # Check for common chapter keywords
        chapter_keywords = [
            'chapter', 'capitulo', 'capítulo', 'part', 'parte',
            'section', 'sección', 'seccion', 'book', 'libro'
        ]
        
        for keyword in chapter_keywords:
            if keyword in text_lower and len(text_lower) < 50:  # Arbitrary length limit
                return True
                
        return False
    
    @classmethod
    def supports_file(cls, file_path: str) -> bool:
        """Check if the file is a PDF"""
        return str(file_path).lower().endswith('.pdf')
