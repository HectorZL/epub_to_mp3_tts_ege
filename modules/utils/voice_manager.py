import asyncio
from typing import List, Dict, Optional
import edge_tts

class VoiceManager:
    def __init__(self):
        self.voices: List[Dict] = []
        self.filtered_voices: List[Dict] = []
        self.loaded = False
        
    async def load_voices_async(self):
        """Load available voices asynchronously"""
        if not self.loaded:
            try:
                voices = await edge_tts.list_voices()
                self.voices = voices
                self._filter_voices()
                self.loaded = True
            except Exception as e:
                print(f"Error loading voices: {e}")
                raise
    
    def _filter_voices(self, languages: Optional[List[str]] = None):
        """Filter voices by language"""
        if languages is None:
            languages = ['es', 'en']  # Default to Spanish and English
            
        self.filtered_voices = [
            v for v in self.voices 
            if any(lang in v['ShortName'].lower() 
                  for lang in languages)
        ]
    
    def get_voice_names(self) -> List[str]:
        """Get list of available voice names"""
        return [v['Name'] for v in self.filtered_voices]
    
    def get_voice_by_name(self, name: str) -> Optional[Dict]:
        """Get voice details by name"""
        for voice in self.filtered_voices:
            if voice['Name'] == name:
                return voice
        return None
