import asyncio
import os
import re
from typing import Optional, Callable, List, Dict, Any
import edge_tts

from modules.utils.voice_manager import VoiceManager

class AudioConverter:
    def __init__(self, voice_manager: VoiceManager):
        self.voice_manager = voice_manager
        self.is_processing = False
        self.is_paused = False
        self.is_cancelled = False
        self.current_process = None
        
    async def convert_text_to_speech(
        self,
        text: str,
        voice_name: str,
        output_file: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """Convert text to speech and save as MP3"""
        # Clean and validate input text
        if not text or not text.strip():
            raise ValueError("El texto está vacío o solo contiene espacios en blanco")
            
        if not voice_name:
            raise ValueError("No se ha seleccionado una voz")
            
        self.is_processing = True
        self.is_paused = False
        self.is_cancelled = False
        
        try:
            # Get the full voice details
            voice = self.voice_manager.get_voice_by_name(voice_name)
            if not voice:
                raise ValueError(f"Voz no encontrada: {voice_name}")
            
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # Clean the text and ensure it has valid content
            text = text.strip()
            if not text:
                raise ValueError("El texto está vacío después de limpiar")
                
            # Split text into smaller chunks to handle large texts
            chunks = self._split_into_chunks(text)
            total_chunks = len(chunks)
            
            if not chunks:
                raise ValueError("No se pudo dividir el texto en fragmentos válidos")
            
            # Temporary files for chunks
            temp_files = []
            
            for i, chunk in enumerate(chunks, 1):
                if self.is_cancelled:
                    self._cleanup_temp_files(temp_files)
                    return False
                    
                while self.is_paused and not self.is_cancelled:
                    await asyncio.sleep(0.5)
                    
                if self.is_cancelled:
                    self._cleanup_temp_files(temp_files)
                    return False
                
                # Skip empty chunks
                if not chunk or not chunk.strip():
                    continue
                    
                # Create temp file for this chunk
                temp_file = f"temp_chunk_{i}.mp3"
                temp_files.append(temp_file)
                
                try:
                    # Convert chunk to speech
                    communicate = edge_tts.Communicate(
                        text=chunk,
                        voice=voice['Name'],
                        rate="+0%",
                        volume="+0%"
                    )
                    
                    # Save chunk to temp file with timeout
                    try:
                        await asyncio.wait_for(communicate.save(temp_file), timeout=300)  # 5 minute timeout
                    except asyncio.TimeoutError:
                        raise Exception("Tiempo de espera agotado al generar el audio. Intente con un texto más corto.")
                    
                    # Verify the output file was created and has content
                    if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
                        raise Exception(f"No se recibió audio para el fragmento {i}. Intente nuevamente.")
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(i, total_chunks)
                        
                except Exception as e:
                    # Clean up any partial files before re-raising
                    self._cleanup_temp_files(temp_files)
                    raise Exception(f"Error procesando el fragmento {i}/{total_chunks}: {str(e)}")
            
            # If no valid chunks were processed
            if not temp_files:
                raise ValueError("No se pudo generar ningún fragmento de audio válido")
            
            # Combine all chunks into the final file
            self._combine_audio_files(temp_files, output_file)
            
            # Verify the final output file
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("No se pudo generar el archivo de audio final")
            
            return True
            
        except Exception as e:
            # Clean up any partial files
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except:
                    pass
            raise
            
        finally:
            self.is_processing = False
            self._cleanup_temp_files(temp_files)
    
    async def convert_file(
        self,
        input_path: str,
        output_path: str,
        voice_name: str,
        rate: str = "+0%",
        volume: str = "+0%",
        selected_chapters: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Convert text file to speech with progress tracking and chapter support"""
        try:
            # Get the extractor for the input file type
            extractor = get_extractor(input_path)
            
            # Extract text or chapters
            result = await extractor.extract_text(input_path)
            
            # Handle both string and chapter-based extraction
            if isinstance(result, str):
                # Single text content
                await self._convert_text(
                    result, 
                    output_path, 
                    voice_name, 
                    rate, 
                    volume,
                    progress_callback
                )
            elif isinstance(result, list):
                # Chapter-based content
                if not result:
                    raise ValueError("No chapters found in the document")
                
                # Filter chapters if specified
                if selected_chapters is not None:
                    # Create a new list with only the selected chapters, but keep their original indices
                    filtered_result = [(i, result[i]) for i in range(len(result)) if i in selected_chapters]
                    result = filtered_result
                else:
                    # If no chapters are selected, include all with their original indices
                    result = list(enumerate(result))
                
                # Convert each chapter
                total_chapters = len(result)
                for i, (original_idx, chapter) in enumerate(result):
                    if progress_callback:
                        # Update progress with original chapter number for better user feedback
                        progress_callback(original_idx + 1, total_chapters)
                    
                    # Create output file for this chapter using the original chapter number and title
                    base, ext = os.path.splitext(output_path)
                    chapter_name = chapter.get('title', f'Capítulo {original_idx + 1}').strip()
                    # Clean the chapter name to avoid invalid filename characters
                    chapter_name = re.sub(r'[\\/*?:"<>|]', "", chapter_name)
                    # Include the original chapter number in the filename
                    chapter_output = f"{base}_Cap{original_idx + 1:02d}_{chapter_name}{ext}"
                    
                    await self._convert_text(
                        chapter['content'],
                        chapter_output,
                        voice_name,
                        rate,
                        volume,
                        None  # No progress for individual chapters
                    )
                
                if progress_callback:
                    progress_callback(total_chapters, total_chapters)
            
        except Exception as e:
            raise Exception(f"Error during conversion: {str(e)}")
    
    async def _convert_text(
        self,
        text: str,
        output_path: str,
        voice_name: str,
        rate: str,
        volume: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Internal method to convert text to speech"""
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Generate TTS
            communicate = edge_tts.Communicate(
                text,
                voice_name,
                rate=rate,
                volume=volume,
            )
            
            # Save to file
            await communicate.save(output_path)
            
            if progress_callback:
                progress_callback(1, 1)
                
        except Exception as e:
            raise Exception(f"Error converting text to speech: {str(e)}")
    
    def _split_into_chunks(self, text: str, max_chars: int = 5000) -> List[str]:
        """Split text into chunks of maximum size, trying to break at sentence boundaries"""
        if len(text) <= max_chars:
            return [text]
            
        chunks = []
        current_chunk = ""
        
        # Split into paragraphs first
        paragraphs = text.split('\n\n')
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            # If paragraph is too long, split into sentences
            if len(para) > max_chars:
                # Simple sentence splitting - could be improved with NLTK for better accuracy
                sentences = para.split('. ')
                current_sentence = ""
                
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                        
                    # Add period if it was removed by split
                    if not sent.endswith('.'):
                        sent += '.'
                        
                    if len(current_sentence) + len(sent) <= max_chars:
                        current_sentence += " " + sent if current_sentence else sent
                    else:
                        if current_sentence:
                            chunks.append(current_sentence)
                        current_sentence = sent
                
                if current_sentence:
                    chunks.append(current_sentence)
            else:
                # If current chunk + paragraph is too big, start a new chunk
                if current_chunk and len(current_chunk) + len(para) + 2 > max_chars:
                    chunks.append(current_chunk)
                    current_chunk = para
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + para
                    else:
                        current_chunk = para
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def _combine_audio_files(self, input_files: List[str], output_file: str):
        """Combine multiple audio files into one"""
        # This is a simple implementation that just concatenates the files
        # For better results, consider using a proper audio library like pydub
        with open(output_file, 'wb') as outfile:
            for fname in input_files:
                try:
                    with open(fname, 'rb') as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    print(f"Warning: Could not read {fname}: {e}")
    
    def _cleanup_temp_files(self, files: List[str]):
        """Clean up temporary files"""
        for f in files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception as e:
                print(f"Warning: Could not delete {f}: {e}")
    
    def pause(self):
        """Pause the current conversion"""
        self.is_paused = True
    
    def resume(self):
        """Resume a paused conversion"""
        self.is_paused = False
    
    def cancel(self):
        """Cancel the current conversion"""
        self.is_cancelled = True
        
        # If there's an ongoing process, try to terminate it
        if self.current_process and self.current_process.is_running():
            try:
                self.current_process.terminate()
            except:
                pass
    
    @property
    def is_processing(self) -> bool:
        """Check if a conversion is in progress"""
        return self._is_processing
    
    @is_processing.setter
    def is_processing(self, value: bool):
        """Set the processing state"""
        self._is_processing = value
        if not value:
            self.is_paused = False
            self.is_cancelled = False
