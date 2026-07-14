import asyncio
import os
import re
import tempfile
from typing import Optional, Callable, List, Dict, Any
import edge_tts

from modules.utils.voice_manager import VoiceManager
from modules.extractors import get_extractor

class AudioConverter:
    def __init__(self, voice_manager: VoiceManager, piper_manager=None, chatterbox_manager=None, kokoro_manager=None):
        self.voice_manager = voice_manager
        self.piper_manager = piper_manager
        self.chatterbox_manager = chatterbox_manager
        self.kokoro_manager = kokoro_manager
        self.engine_mode = "online"   # 'online' | 'offline' | 'chatterbox' | 'kokoro'
        self.is_processing = False
        self.is_paused = False
        self.is_cancelled = False
        self.current_process = None
        
    async def convert_text_to_speech(
        self,
        text: str,
        voice_name: str,
        output_file: str,
        rate: str = "-10%",
        volume: str = "+0%",
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
        
        temp_files = []
        temp_dir = None
        success = False
        
        try:
            # Get the full voice details (only needed for edge-tts)
            if self.engine_mode in ["offline", "chatterbox", "kokoro"]:
                voice = {"Name": voice_name}
            else:
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
                
            # Split text into smaller chunks to handle large texts safely depending on the engine
            if self.engine_mode == "chatterbox":
                max_chars = 200  # Chatterbox fails/stops early with long texts
            elif self.engine_mode == "kokoro":
                max_chars = 400  # Kokoro works well with medium chunks
            elif self.engine_mode == "offline":
                max_chars = 1000  # Piper works well with medium chunks
            else:
                max_chars = 5000  # edge-tts (online) can handle larger chunks
                
            chunks = self._split_into_chunks(text, max_chars=max_chars)
            total_chunks = len(chunks)
            
            if not chunks:
                raise ValueError("No se pudo dividir el texto en fragmentos válidos")
            
            # Create a dedicated temp directory for this output file's chunks
            base_dir = os.path.dirname(os.path.abspath(output_file))
            output_filename = os.path.basename(output_file)
            temp_dir = os.path.join(base_dir, f".temp_{output_filename}_chunks")
            os.makedirs(temp_dir, exist_ok=True)

            # Prepare chunks and associate with temp file names
            tasks_data = []
            for i, chunk in enumerate(chunks, 1):
                if chunk and chunk.strip():
                    temp_file = os.path.join(temp_dir, f"chunk_{i}.mp3")
                    tasks_data.append((i, chunk, temp_file))
            
            # If no valid chunks were processed
            if not tasks_data:
                raise ValueError("No se pudo generar ningún fragmento de audio válido")
            
            temp_files = [item[2] for item in tasks_data]
            total_chunks = len(tasks_data)
            
            # Use Semaphore to control concurrency levels
            concurrency_limit = 3 if self.engine_mode == "online" else 2
            sem = asyncio.Semaphore(concurrency_limit)
            
            completed_chunks = 0
            progress_lock = asyncio.Lock()
            
            async def process_task(i, chunk, temp_file):
                nonlocal completed_chunks
                
                async with sem:
                    if self.is_cancelled:
                        return
                        
                    while self.is_paused and not self.is_cancelled:
                        await asyncio.sleep(0.5)
                        
                    if self.is_cancelled:
                        return
                    
                    # Si el fragmento ya existe y no está vacío, lo reutilizamos directamente
                    if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                        print(f"Reutilizando fragmento de audio existente: {temp_file}")
                        async with progress_lock:
                            completed_chunks += 1
                            if progress_callback:
                                progress_callback(completed_chunks, total_chunks)
                        return

                    try:
                        # --- PROSODIA HEURÍSTICA Y SENTIMIENTOS ---
                        current_rate = rate  # from method definition fallback (-10%)
                        current_pitch = "+0Hz"
                        current_volume = volume # from method definition
                        
                        if "!" in chunk or "¡" in chunk:
                            current_pitch = "+10Hz"
                            current_rate = "+0%"  # Accelerates due to exclamation
                        elif "?" in chunk or "¿" in chunk:
                            current_pitch = "+5Hz"
                        elif '"' in chunk or "—" in chunk or "«" in chunk or "-" in chunk:
                            current_pitch = "+2Hz"
                            current_volume = "+5%"
                            
                        if self.engine_mode == "offline" and self.piper_manager:
                            # ── Piper offline ─────────────────────────────────
                            def run_piper():
                                tmp_wav = os.path.splitext(temp_file)[0] + ".wav"
                                self.piper_manager.synthesize(chunk, voice_name, tmp_wav)
                                self.piper_manager.wav_to_mp3(tmp_wav, temp_file)
                                try:
                                    os.remove(tmp_wav)
                                except Exception:
                                    pass
                            await asyncio.get_event_loop().run_in_executor(None, run_piper)
                            
                        elif self.engine_mode == "chatterbox" and self.chatterbox_manager:
                            # ── Chatterbox offline ────────────────────────────
                            def run_chatterbox():
                                tmp_wav = os.path.splitext(temp_file)[0] + ".wav"
                                audio_prompt = None if voice_name == "default" else voice_name
                                self.chatterbox_manager.synthesize(chunk, tmp_wav, audio_prompt_path=audio_prompt)
                                # Reutilizar el convertidor de wav_to_mp3 de piper_manager si existe
                                if self.piper_manager:
                                    self.piper_manager.wav_to_mp3(tmp_wav, temp_file)
                                else:
                                    # Fallback si piper_manager no está disponible
                                    import soundfile as sf
                                    data, samplerate = sf.read(tmp_wav)
                                    sf.write(temp_file, data, samplerate, format='MP3', subtype='MPEG_LAYER_III')
                                try:
                                    os.remove(tmp_wav)
                                except Exception:
                                    pass
                            await asyncio.get_event_loop().run_in_executor(None, run_chatterbox)
                            
                        elif self.engine_mode == "kokoro" and self.kokoro_manager:
                            # ── Kokoro offline ────────────────────────────────
                            def run_kokoro():
                                tmp_wav = os.path.splitext(temp_file)[0] + ".wav"
                                self.kokoro_manager.synthesize(chunk, voice_name, tmp_wav)
                                # Reutilizar el convertidor de wav_to_mp3 de piper_manager si existe
                                if self.piper_manager:
                                    self.piper_manager.wav_to_mp3(tmp_wav, temp_file)
                                else:
                                    # Fallback si piper_manager no está disponible
                                    import soundfile as sf
                                    data, samplerate = sf.read(tmp_wav)
                                    sf.write(temp_file, data, samplerate, format='MP3', subtype='MPEG_LAYER_III')
                                try:
                                    os.remove(tmp_wav)
                                except Exception:
                                    pass
                            await asyncio.get_event_loop().run_in_executor(None, run_kokoro)
                            
                        else:
                            # ── edge-tts online ───────────────────────────────
                            # Truco SSML para pausas invisibles
                            chunk_text = chunk + "...\n\n"
                            communicate = edge_tts.Communicate(
                                text=chunk_text,
                                voice=voice['Name'],
                                rate=current_rate,
                                volume=current_volume,
                                pitch=current_pitch
                            )
                            try:
                                await asyncio.wait_for(communicate.save(temp_file), timeout=300)
                            except asyncio.TimeoutError:
                                raise Exception("Tiempo de espera agotado al generar el audio. Intente con un texto mas corto.")
                        
                        # Verify the output file was created and has content
                        if not os.path.exists(temp_file) or os.path.getsize(temp_file) == 0:
                            raise Exception(f"No se recibió audio para el fragmento {i}. Intente nuevamente.")
                        
                        # Update progress safely
                        async with progress_lock:
                            completed_chunks += 1
                            if progress_callback:
                                progress_callback(completed_chunks, total_chunks)
                                
                    except Exception as e:
                        raise Exception(f"Error procesando el fragmento {i}/{total_chunks}: {str(e)}")
 
            # Run all tasks concurrently
            tasks = [process_task(i, chunk, temp_file) for i, chunk, temp_file in tasks_data]
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                # No eliminamos los archivos parciales aquí para poder reanudar el trabajo en caso de fallo
                raise
            
            # Combine all chunks into the final file
            self._combine_audio_files(temp_files, output_file)
            
            # Verify the final output file
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception("No se pudo generar el archivo de audio final")
            
            success = True
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
            # Solo limpiamos los fragmentos si la conversión de este lote fue completamente exitosa
            if success:
                self._cleanup_temp_files(temp_files)
                try:
                    if temp_dir and os.path.exists(temp_dir) and not os.listdir(temp_dir):
                        os.rmdir(temp_dir)
                except Exception as e:
                    print(f"Warning: Could not remove temp directory {temp_dir}: {e}")
    
    async def convert_file(
        self,
        input_path: str,
        output_path: str,
        voice_name: str,
        rate: str = "-10%",
        volume: str = "+0%",
        selected_chapters: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        join_chapters: bool = True,
        keep_chapters: bool = True,
    ) -> None:
        """Convert text file to speech with progress tracking and chapter support"""
        try:
            if selected_chapters:
                chap_numbers = [idx + 1 for idx in selected_chapters]
                min_chap = min(chap_numbers)
                max_chap = max(chap_numbers)
                suffix = f"_{min_chap}_{max_chap}" if min_chap != max_chap else f"_{min_chap}"
                base, ext = os.path.splitext(output_path)
                output_path = f"{base}{suffix}{ext}"

            # Get the extractor for the input file type
            extractor = get_extractor(input_path)
            
            # Extract text or chapters
            result = await extractor.extract_text(input_path)
            
            # Handle both string and chapter-based extraction
            if isinstance(result, str):
                # Single text content
                await self.convert_text_to_speech(
                    text=result, 
                    voice_name=voice_name,
                    output_file=output_path, 
                    rate=rate, 
                    volume=volume,
                    progress_callback=progress_callback
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
                chapter_files = []
                for i, (original_idx, chapter) in enumerate(result):
                    chapter_content = chapter.get('content', '')
                    if not chapter_content or not chapter_content.strip():
                        print(f"Saltando capítulo vacío {original_idx + 1} ({chapter.get('title', 'Sin título')})")
                        if progress_callback:
                            progress_callback(original_idx + 1, total_chapters)
                        continue

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
                    
                    # Si el archivo del capítulo ya existe y no está vacío, lo omitimos
                    if os.path.exists(chapter_output) and os.path.getsize(chapter_output) > 0:
                        print(f"Capítulo ya convertido, reutilizando: {chapter_output}")
                        chapter_files.append(chapter_output)
                        continue

                    await self.convert_text_to_speech(
                        text=chapter_content,
                        voice_name=voice_name,
                        output_file=chapter_output,
                        rate=rate,
                        volume=volume,
                        progress_callback=None  # No progress for individual chapters
                    )
                    chapter_files.append(chapter_output)
                
                # Merge chapters if requested
                if join_chapters and chapter_files:
                    self._combine_audio_files(chapter_files, output_path)
                    if not keep_chapters:
                        for f in chapter_files:
                            try:
                                if os.path.exists(f):
                                    os.remove(f)
                            except Exception as e:
                                print(f"Warning: Could not remove chapter file {f}: {e}")

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
        if len(text) <= max_chars and self.engine_mode not in ["offline", "chatterbox", "kokoro"]:
            return [text]
            
        chunks = []
        current_chunk = ""
        
        # Split into paragraphs first
        paragraphs = text.split('\n\n')
        
        prevent_merge = self.engine_mode in ["offline", "chatterbox", "kokoro"]
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            # If paragraph is too long, split into sentences
            if len(para) > max_chars:
                # Splitting by sentence boundary (. ! ?) while ignoring common abbreviations to prevent context breakage
                # Negative lookbehinds for Dr, Sr, Sra, Mr, Ms, Prof, etc.
                split_regex = r'(?<!\bDr)(?<!\bSr)(?<!\bSra)(?<!\bMr)(?<!\bMs)(?<!\bProf)(?<!\bSt)(?<=[.!?])\s+'
                sentences = re.split(split_regex, para)
                current_sentence = ""
                
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                        
                    if len(current_sentence) + len(sent) + 1 <= max_chars:
                        current_sentence += " " + sent if current_sentence else sent
                    else:
                        if current_sentence:
                            chunks.append(current_sentence)
                        current_sentence = sent
                
                if current_sentence:
                    chunks.append(current_sentence)
            else:
                if prevent_merge:
                    # Do not merge separate paragraphs for offline/chatterbox to preserve paragraph-level pause
                    chunks.append(para)
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
        
        # Add the last chunk if not empty and we were merging
        if not prevent_merge and current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def _combine_audio_files(self, input_files: List[str], output_file: str):
        """Combine multiple audio files into one"""
        if not input_files:
            return

        # Verificar si el contenido real son archivos WAV
        is_wav = False
        with open(input_files[0], 'rb') as f:
            if f.read(4) == b'RIFF':
                is_wav = True

        if is_wav:
            import wave
            with wave.open(output_file, 'wb') as outfile:
                for i, fname in enumerate(input_files):
                    try:
                        with wave.open(fname, 'rb') as infile:
                            if i == 0:
                                outfile.setparams(infile.getparams())
                            outfile.writeframes(infile.readframes(infile.getnframes()))
                    except Exception as e:
                        print(f"Warning: Could not read {fname}: {e}")
        else:
            # Archivos MP3 (edge-tts) se pueden concatenar directamente uniendo bytes
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
