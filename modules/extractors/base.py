import re
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
        """Clean up text by removing extra whitespace, normalizing newlines, and removing unwanted patterns"""
        if not text:
            return ""
        
        # First, remove URLs and web addresses
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', ' ', text)
        text = re.sub(r'www\.[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', ' ', text)
        
        # Remove bracketed or braced text (like [note] or {reference})
        text = re.sub(r'\[.*?\]', ' ', text)
        text = re.sub(r'\{.*?\}', ' ', text)
        
        # Clean up any patterns that could lead to repeated characters
        text = re.sub(r'\s*[=_-]+\s*', ' ', text)  # Remove sequences of =, -, _ with spaces around them
        # Remove spaced out zeros or similar artifacts (e.g. 0 0 0 0)
        text = re.sub(r'(\b0\s+){2,}0\b', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)  # Replace multiple spaces with single space
        
        # Split into lines and process each line
        lines = []
        for line in text.splitlines():
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Skip lines that are just separators or special characters
            if re.fullmatch(r'^[=_-]{2,}$', line) or re.fullmatch(r'^[\W_]+$', line):
                continue
                
            # Ensure long strings of dots like ..... become ... (ellipsis) for natural pause
            line = re.sub(r'\.{3,}', '... ', line)
            
            # Clean up standalone zero glitches (e.g., 000, 0000) that confuse TTS
            line = re.sub(r'\b0{2,}\b', ' ', line)
            
            # Replace lines with too many repeated non-alphanumeric characters (more than 3) with a comma for pacing
            line = re.sub(r'([^\w\s.,!?])\1{2,}', ', ', line)
            
            # For letters, reduce excessive repetition (e.g., "Ahhhhh" to "Ahhh") to help TTS without dropping the line
            line = re.sub(r'([a-zA-Z])\1{3,}', r'\1\1\1', line)
            
            # Clean up any remaining unwanted patterns in the line
            line = re.sub(r'\s*[=_-]+\s*', ' ', line)  # Clean up any remaining separators
            line = re.sub(r'\s{2,}', ' ', line)  # Normalize spaces
            
            if line.strip():
                # Enforce trailing punctuation for proper breathing capability in TTS engines
                # If the line ends with a letter, number, or closing quote, add a period.
                if re.search(r'[a-zA-Z0-9"\'»]$', line):
                    line += '.'
                lines.append(line)
        
        # Join with single newlines and clean up spaces
        text = ' '.join(lines)
        
        # Final cleanup of any remaining unwanted patterns
        text = re.sub(r'\s*[=_-]+\s*', ' ', text)  # Remove any remaining separators
        text = re.sub(r'\s*([.,;:!?])(?=[a-zA-Z])', r'\1 ', text)  # Fix missing spacing after punctuation: "Hola.Como" -> "Hola. Como"
        text = re.sub(r'\s+', ' ', text).strip()  # Final whitespace cleanup
        
        return text
