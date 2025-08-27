import os
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
import edge_tts

from modules.utils.voice_manager import VoiceManager

class AudioConverter:
    def __init__(self, voice_manager: VoiceManager):
        self.voice_manager = voice_manager
        self.temp_dir: Optional[Path] = None
        self.is_paused = False
        self.is_cancelled = False
        self.current_process = None
        
    async def _create_temp_dir(self, base_name: str) -> Path:
        """Create a temporary directory for conversion files"""
        if self.temp_dir is None:
            temp_dir = Path(tempfile.mkdtemp(prefix=f"tts_{base_name}_"))
            self.temp_dir = temp_dir
        return self.temp_dir
        
    def cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
    
    async def convert_text_to_speech(
        self,
        text: str,
        voice_name: str,
        output_file: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        chunk_size: int = 5000
    ) -> bool:
        """
        Convert text to speech with progress tracking and pause/resume support
        """
        try:
            # Create a unique identifier for this conversion
            base_name = Path(output_file).stem
            temp_dir = await self._create_temp_dir(base_name)
            
            # Split text into chunks
            chunks = self._split_into_chunks(text, chunk_size)
            total_chunks = len(chunks)
            temp_files = []
            
            # Process each chunk
            for i, chunk in enumerate(chunks, 1):
                if self.is_cancelled:
                    self.cleanup()
                    return False
                    
                while self.is_paused:
                    await asyncio.sleep(0.5)
                    
                temp_file = str(temp_dir / f"chunk_{i:04d}.mp3")
                await self._convert_chunk(chunk, voice_name, temp_file)
                temp_files.append(temp_file)
                
                if progress_callback:
                    progress_callback(i, total_chunks)
            
            # Combine all chunks
            await self._combine_audio_files(temp_files, output_file)
            return True
            
        except Exception as e:
            print(f"Error during conversion: {e}")
            return False
        finally:
            self.cleanup()
    
    def pause(self):
        """Pause the current conversion"""
        self.is_paused = True
    
    def resume(self):
        """Resume a paused conversion"""
        self.is_paused = False
    
    def cancel(self):
        """Cancel the current conversion"""
        self.is_cancelled = True
        self.cleanup()
    
    async def _convert_chunk(self, text: str, voice_name: str, output_file: str):
        """Convert a single chunk of text to speech"""
        voice = self.voice_manager.get_voice_by_name(voice_name)
        if not voice:
            raise ValueError(f"Voice not found: {voice_name}")
            
        communicate = edge_tts.Communicate(text, voice=voice_name)
        await communicate.save(output_file)
    
    @staticmethod
    def _split_into_chunks(text: str, chunk_size: int) -> List[str]:
        """Split text into chunks of specified size, trying to break at sentence boundaries"""
        if not text.strip():
            return []
            
        # Replace multiple whitespace with single space
        text = ' '.join(text.split())
        
        # Split into sentences (simple approach)
        sentences = []
        current_sentence = []
        
        for word in text.split():
            current_sentence.append(word)
            if word.endswith(('.', '!', '?')):
                sentences.append(' '.join(current_sentence))
                current_sentence = []
        
        if current_sentence:
            sentences.append(' '.join(current_sentence))
        
        # Group sentences into chunks
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            if current_length + sentence_length > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
                
            current_chunk.append(sentence)
            current_length += sentence_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
            
        return chunks
    
    @staticmethod
    async def _combine_audio_files(input_files: List[str], output_file: str):
        """Combine multiple audio files into one"""
        if not input_files:
            return
            
        # Simple file concatenation (for MP3, this might not work perfectly)
        with open(output_file, 'wb') as outfile:
            for fname in input_files:
                with open(fname, 'rb') as infile:
                    outfile.write(infile.read())
