from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Union
import asyncio

class BaseExtractor(ABC):
    """Base class for all text extractors"""
    
    @abstractmethod
    async def extract_text(self, file_path: str) -> Union[str, List[Dict[str, Any]]]:
        """Extract text from the file
        
        Returns:
            Either a string with all text or a list of dictionaries with 'title' and 'content' for each chapter
        """
        pass
    
    async def get_chapters(self, file_path: str) -> List[str]:
        """Get chapter information from the file.
        Returns a list of chapter titles.
        """
        result = await self.extract_text(file_path)
        if isinstance(result, list):
            return [chap.get('title', f'Chapter {i+1}') for i, chap in enumerate(result)]
        return []
    
    async def extract_chapter(self, file_path: str, chapter_index: int) -> Optional[str]:
        """Extract text for a specific chapter"""
        result = await self.extract_text(file_path)
        if isinstance(result, list) and 0 <= chapter_index < len(result):
            return result[chapter_index].get('content')
        return None
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean up text by removing extra whitespace and normalizing newlines"""
        if not text:
            return ""
            
        # Replace multiple whitespace with single space
        text = ' '.join(text.split())
        # Normalize newlines
        text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
        return text
