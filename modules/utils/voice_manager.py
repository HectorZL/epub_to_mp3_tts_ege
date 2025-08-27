import asyncio
from typing import List, Dict, Optional, Set
import edge_tts

class VoiceManager:
    def __init__(self):
        self.voices: List[Dict] = []
        self.filtered_voices: List[Dict] = []
        self.loaded = False
        self.supported_languages = {'es', 'en'}  # Spanish and English only
        
    async def load_voices_async(self):
        """Load available voices asynchronously with language and gender filtering"""
        if not self.loaded:
            try:
                all_voices = await edge_tts.list_voices()
                
                # Filter voices by supported languages and add gender info
                self.voices = []
                for voice in all_voices:
                    # Extract language code (e.g., 'es-ES' -> 'es')
                    lang_code = voice['ShortName'].split('-')[0].lower()
                    
                    # Only keep Spanish and English voices
                    if lang_code in self.supported_languages:
                        # Add gender information
                        voice_data = {
                            'Name': voice['Name'],
                            'ShortName': voice['ShortName'],
                            'Gender': voice.get('Gender', 'Unknown').lower(),
                            'Language': lang_code
                        }
                        self.voices.append(voice_data)
                
                # Apply default filters
                self._filter_voices()
                self.loaded = True
                
            except Exception as e:
                print(f"Error loading voices: {e}")
                raise
    
    def _filter_voices(self, 
                      languages: Optional[Set[str]] = None,
                      gender: Optional[str] = None):
        """Filter voices by language and gender"""
        self.filtered_voices = []
        
        # If no languages specified, use all supported languages
        if not languages:
            languages = self.supported_languages
        
        # First filter by exact language match (e.g., 'es' matches 'es-ES', 'es-MX')
        for voice in self.voices:
            voice_lang = voice['ShortName'].split('-')[0].lower()
            if voice_lang in languages:
                self.filtered_voices.append(voice)
        
        # Then apply gender filter if specified
        if gender and gender.lower() in ['male', 'female']:
            gender = gender.lower()
            self.filtered_voices = [
                v for v in self.filtered_voices
                if v['Gender'].lower() == gender
            ]
    
    def get_voice_names(self) -> List[str]:
        """Get list of available voice names"""
        return [v['Name'] for v in self.filtered_voices]
    
    def get_voice_by_name(self, name: str) -> Optional[Dict]:
        """Get voice details by name"""
        for voice in self.voices:  # Search in all voices, not just filtered
            if voice['Name'] == name:
                return voice
        return None
    
    def get_available_genders(self) -> List[str]:
        """Get list of available genders in filtered voices"""
        genders = set()
        for voice in self.filtered_voices:
            if voice['Gender'] in ['male', 'female']:
                genders.add(voice['Gender'].capitalize())
        return sorted(list(genders))
    
    def update_filters(self, language: Optional[str] = None, 
                      gender: Optional[str] = None):
        """Update voice filters and refresh the filtered list"""
        languages = {language} if language else self.supported_languages
        self._filter_voices(languages, gender.lower() if gender else None)
