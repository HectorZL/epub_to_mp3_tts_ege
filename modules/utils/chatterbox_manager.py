"""
Gestor de Chatterbox TTS (offline con GPU).
Maneja la detección de dependencias, instalación automática, carga del modelo y síntesis.
"""
import sys
import subprocess
from pathlib import Path
from typing import Optional, Callable

class ChatterboxVoiceManager:
    def __init__(self):
        self.model = None
        self.device = "cpu"
        self._is_loading = False

    def is_available(self) -> bool:
        """Verifica si las librerías necesarias están instaladas."""
        try:
            import torch
            import torchaudio
            import chatterbox
            return True
        except ImportError:
            return False

    def check_cuda(self) -> bool:
        """Verifica si CUDA está disponible para aceleración por GPU."""
        if not self.is_available():
            return False
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def install_dependencies(self, progress_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Instala las dependencias necesarias mediante pip."""
        dependencies = ["torch", "torchaudio", "chatterbox-tts"]
        
        if progress_callback:
            progress_callback("Iniciando instalación de componentes de IA local...")

        try:
            # Determinamos si el entorno es virtual
            pip_cmd = [sys.executable, "-m", "pip", "install"]
            
            # Intentar instalar torch y torchaudio con soporte CUDA si es posible
            if progress_callback:
                progress_callback("Instalando PyTorch y torchaudio con soporte CUDA...")
                
            # Para la RTX 3060 del usuario, se recomienda CUDA 12.1 o compatible para acelerar por GPU
            install_args = pip_cmd + dependencies + ["--index-url", "https://download.pytorch.org/whl/cu121", "--extra-index-url", "https://pypi.org/simple"]
            
            # Ejecutar instalación de forma síncrona dentro del hilo
            process = subprocess.Popen(
                install_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if progress_callback:
                        progress_callback(line.strip())
                        
            process.wait()
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback("¡Instalación completada con éxito!")
                return True
            else:
                if progress_callback:
                    progress_callback(f"La instalación falló con código de salida: {process.returncode}")
                return False
                
        except Exception as e:
            if progress_callback:
                progress_callback(f"Error durante la instalación: {str(e)}")
            return False

    def _load_model(self):
        """Carga el modelo en memoria (Lazy Loading)."""
        if self.model is not None:
            return

        if not self.is_available():
            raise ImportError(
                "Chatterbox o PyTorch no están instalados. "
                "Por favor, instala las dependencias desde el panel de Chatterbox."
            )

        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Cargando Chatterbox-Turbo TTS en dispositivo: {self.device}...")
        
        # Carga el modelo desde Hugging Face (lo descarga en el primer uso)
        self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
        
        # Convertir submodelos a bfloat16 si estamos en CUDA para optimizar memoria y velocidad
        if self.device == "cuda":
            try:
                self.model.t3.to(dtype=torch.bfloat16)
                self.model.conds.t3.to(dtype=torch.bfloat16)
                print("Modelo Chatterbox-Turbo convertido a bfloat16 para optimizar VRAM.")
            except Exception as e:
                print(f"Advertencia: No se pudo convertir submodelos de Chatterbox a bfloat16: {e}")

        print("Modelo Chatterbox-Turbo cargado correctamente.")

    def synthesize(
        self,
        text: str,
        output_wav: str,
        audio_prompt_path: Optional[str] = None
    ):
        """
        Sintetiza texto a audio WAV usando Chatterbox.
        Si se pasa audio_prompt_path, realiza clonación de voz.
        """
        self._load_model()
        
        import torch
        import torchaudio
        import gc
        import contextlib

        # Limpieza de texto de Chatterbox (remueve corchetes no soportados o caracteres inválidos)
        # Permite etiquetas de paralingüística nativas de Chatterbox: [laugh], [sigh], [cough], [chuckle]
        # Pero filtramos otras cosas que puedan confundir al modelo
        clean_text = text.strip()

        # Determinar si usamos autocast
        use_autocast = (self.device == "cuda")
        autocast_ctx = torch.autocast(device_type="cuda", dtype=torch.bfloat16) if use_autocast else contextlib.nullcontext()

        try:
            with torch.inference_mode():
                with autocast_ctx:
                    if audio_prompt_path and Path(audio_prompt_path).exists():
                        print(f"Sintetizando Chatterbox con clonación desde: {audio_prompt_path}")
                        
                        # Normalizar audio de referencia a mono, 24kHz, duración entre 5.2s y 10s
                        import torchaudio
                        import torchaudio.transforms as T
                        import tempfile
                        import warnings
                        
                        if not hasattr(self, '_trimmed_prompts'):
                            self._trimmed_prompts = {}
                            
                        if str(audio_prompt_path) in self._trimmed_prompts:
                            prompt_to_use = self._trimmed_prompts[str(audio_prompt_path)]
                        else:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore")
                                try:
                                    print(f"Normalizando audio de referencia: {audio_prompt_path}")
                                    waveform, sample_rate = torchaudio.load(str(audio_prompt_path))
                                    
                                    # 1. Mezclar a mono si es estéreo
                                    if waveform.shape[0] > 1:
                                        waveform = waveform.mean(dim=0, keepdim=True)
                                        
                                    # 2. Redefinir frecuencia de muestreo a 24000 Hz (frecuencia nativa de Chatterbox)
                                    target_sr = 24000
                                    if sample_rate != target_sr:
                                        resampler = T.Resample(orig_freq=sample_rate, new_freq=target_sr)
                                        waveform = resampler(waveform)
                                        sample_rate = target_sr
                                        
                                    # 3. Asegurar duración mínima de 5.2 segundos para evitar aserción interna del modelo
                                    duration = waveform.shape[1] / sample_rate
                                    if duration < 5.2:
                                        repeats = int(5.2 / duration) + 1
                                        waveform = waveform.repeat(1, repeats)
                                        duration = waveform.shape[1] / sample_rate
                                        
                                    # 4. Limitar a máximo 10 segundos para prevenir desbordamiento de memoria GPU (OOM)
                                    max_frames = int(10.0 * sample_rate)
                                    if waveform.shape[1] > max_frames:
                                        waveform = waveform[:, :max_frames]
                                        
                                    # 5. Guardar el prompt normalizado como archivo WAV temporal único
                                    temp_prompt_path = Path(tempfile.gettempdir()) / f"normalized_chatterbox_prompt_{id(self)}.wav"
                                    torchaudio.save(str(temp_prompt_path), waveform, sample_rate)
                                    prompt_to_use = str(temp_prompt_path)
                                    print(f"Audio de referencia normalizado con éxito: {prompt_to_use}")
                                    
                                except Exception as e:
                                    print(f"Advertencia al procesar audio de referencia: {e}. Usando el original.")
                                    prompt_to_use = str(audio_prompt_path)
                            
                            self._trimmed_prompts[str(audio_prompt_path)] = prompt_to_use


                        if not hasattr(self, '_current_prompt') or self._current_prompt != prompt_to_use:
                            print(f"Normalizando y preparando condicionales de clonación de voz (una sola vez)...")
                            self.model.prepare_conditionals(prompt_to_use)
                            self._current_prompt = prompt_to_use
                        
                        audio = self.model.generate(
                            clean_text
                        )
                    else:
                        print("Sintetizando Chatterbox con voz predeterminada...")
                        audio = self.model.generate(clean_text)

                # Guardar el tensor generado como WAV (Chatterbox produce audio a 24000 Hz)
                # Nos aseguramos de que el tensor tenga el formato correcto (1, num_samples)
                if len(audio.shape) == 1:
                    audio = audio.unsqueeze(0)
                
                # Mover tensor a CPU
                audio_cpu = audio.to("cpu")
                
                # --- AÑADIR DIGITAL SILENCE / PAUSA PARA RESPIRACIÓN ---
                # Agrega 0.4 segundos de silencio al final de cada fragmento
                # Esto da espacio a las comas y pausas naturales entre fragmentos.
                silence_duration = 0.4
                silence_samples = int(24000 * silence_duration)
                silence_tensor = torch.zeros((1, silence_samples), dtype=audio_cpu.dtype)
                audio_cpu = torch.cat([audio_cpu, silence_tensor], dim=1)
                
                torchaudio.save(output_wav, audio_cpu, sample_rate=24000, encoding="PCM_S", bits_per_sample=16)
                print(f"Audio guardado correctamente en: {output_wav}")

        except Exception as e:
            raise Exception(f"Error en la síntesis con Chatterbox: {str(e)}")
        finally:
            # Liberar activamente VRAM y memoria RAM
            if self.device == "cuda":
                torch.cuda.empty_cache()
            gc.collect()
