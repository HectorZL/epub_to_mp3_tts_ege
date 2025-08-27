# Conversor de Libros a Audio

Aplicación de escritorio para convertir archivos PDF y EPUB a archivos de audio MP3 utilizando la tecnología de texto a voz de Microsoft Edge.

## Características

- Interfaz gráfica moderna y fácil de usar
- Soporte para archivos PDF y EPUB
- Selección de diferentes voces disponibles
- Procesamiento por lotes (convierte libros completos)
- Barra de progreso para seguir el avance de la conversión

## Requisitos

- Python 3.7 o superior
- Conexión a Internet (para descargar las voces de Microsoft Edge)

## Instalación

1. Clona este repositorio o descarga los archivos
2. Crea un entorno virtual (recomendado):
   ```
   python -m venv venv
   venv\Scripts\activate  # En Windows
   source venv/bin/activate  # En Linux/Mac
   ```
3. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Uso

1. Ejecuta la aplicación:
   ```
   python main.py
   ```
2. Haz clic en "Examinar..." para seleccionar un archivo PDF o EPUB
3. Selecciona una voz del menú desplegable
4. Haz clic en "Convertir a MP3"
5. Espera a que se complete la conversión
6. El archivo de audio se guardará en la misma carpeta que el archivo de origen con extensión .mp3

## Notas

- La primera vez que se ejecuta la aplicación, puede tardar unos segundos en cargar las voces disponibles
- Los archivos grandes pueden tardar varios minutos en procesarse
- La calidad del audio depende de la voz seleccionada

## Solución de problemas

Si la aplicación no se inicia correctamente, asegúrate de que:
- Tienes instaladas todas las dependencias
- Tienes conexión a Internet para cargar las voces
- Tienes permisos de escritura en la carpeta de destino

## Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo LICENSE para más detalles.
