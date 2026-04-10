# Conversor de Libros a Audio

Aplicación de escritorio para convertir archivos PDF y EPUB a archivos de audio MP3. Soporta tanto síntesis online (Microsoft Edge TTS) como offline (Piper TTS).

## Características

- Interfaz gráfica moderna y fácil de usar (Tema oscuro adaptativo)
- Soporte para archivos `.pdf` y `.epub`
- Conversión por capítulos (permite seleccionar la conversión de partes específicas del libro)
- **Modo Online**: Utiliza las voces neuronales de alta calidad de Microsoft Edge TTS (requiere conexión a internet activa para sintetizar).
- **Modo Offline**: Utiliza Piper TTS para generación de audio local de altísima velocidad y sin requerir internet. Al seleccionar este modo, la app descarga el modelo una sola vez y lo procesa en local de forma ilimitada y sin bloqueos de red.
- Procesamiento por lotes y barra de progreso detallada.

## Requisitos

- Python 3.7+
- (Recomendado) `ffmpeg` para acelerar la conversión final a MP3 en el modo Offline.

## Instalación

1. Clona este repositorio o descarga los archivos.
2. Crea un entorno virtual (recomendado):
   ```bash
   python -m venv .venv
   
   # En Windows:
   .venv\Scripts\activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

1. Ejecuta la aplicación:
   ```bash
   python main.py
   ```
2. **Selecciona el Motor TTS:**
   - **Online (edge-tts):** Selecciona el idioma, el género y la voz en la nube de Edge que más te guste.
   - **Offline (Piper):** Selecciona el idioma y elige una de las voces locales. Si no tienes alojado el modelo aún, pulsa "Descargar modelo".
3. Haz clic en **Examinar...** para seleccionar un archivo PDF o EPUB.
4. Opcionalmente, usa **"Seleccionar Capítulos"** para omitir partes del libro.
5. Haz clic en **"Convertir a MP3"**. Se generará el audio en el mismo directorio del archivo original.

## Compilar Ejecutable (Windows)

Si deseas empaquetarlo en un solitario archivo `.exe` para no requerir tener Python instalado en el uso diario:

```bash
python build.py
```
*(Durante la compilación la app instalará PyInstaller automáticamente y firmará el ejecutable de forma local si estás en Windows 10/11).*

El binario resultante se encontrará en la carpeta `dist/`. Ten en cuenta que si usas el modo offline, la aplicación descargará los modelos de Piper en una carpeta local llamada `piper_models/` adyacente a donde se ejecute.

## Licencia

Este proyecto está bajo la Licencia MIT.
