import os
import re
import zipfile
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import asyncio
import urllib.parse

from .base import BaseExtractor

class EPUBExtractor(BaseExtractor):
    """Extracts text from EPUB files with chapter support"""
    
    def __init__(self):
        self.container_path = "META-INF/container.xml"
        self.root_dir = ""
        self.opf_path = ""
        self.ncx_path = ""
        self.manifest: Dict[str, Dict[str, str]] = {}
        self.spine: List[str] = []
        self.toc: List[Dict[str, str]] = []
        self.id_to_href: Dict[str, str] = {}
    
    def _resolve_path(self, base_path: str, href: str) -> str:
        """Resolve a relative path against a base path"""
        if not href:
            return ""
        # Handle URI encoding/decoding
        href = urllib.parse.unquote(href)
        # Join and normalize the path
        return os.path.normpath(os.path.join(os.path.dirname(base_path), href)).replace('\\', '/')
    
    def _get_chapter_key(self, filename: str) -> str:
        """Extract a key to group related chapter files"""
        # Remove file extension
        base_name = os.path.splitext(filename)[0]
        
        # Pattern 1: Files like '0001_0000' or '0001_0001' -> extract first part
        match = re.match(r'^(\d{4})_\d+$', base_name)
        if match:
            return f"chapter_{match.group(1)}"
            
        # Pattern 2: Files with chapter names and numbers like 'El_primer_laberinto_0002_0000'
        match = re.match(r'^([a-zA-Z_]+)_(\d{4})_\d+$', base_name)
        if match:
            return f"chapter_{match.group(2)}"  # Use just the number part as key
            
        # For other files, use the base name as key
        return base_name

    def _normalize_chapter_name(self, name: str) -> str:
        """Normalize chapter name by removing sequence numbers and extra spaces"""
        if not name:
            return "Untitled"
            
        # Remove file extension
        name = os.path.splitext(name)[0]
        
        # Pattern 1: Files like '0001_0000' or '0001_0001' -> extract first part
        match = re.match(r'^(\d{4})_\d+$', name)
        if match:
            return f"Chapter {int(match.group(1)):02d}"
            
        # Pattern 2: Files with chapter names and numbers like 'El_primer_laberinto_0002_0000'
        match = re.match(r'^([a-zA-Z_]+)_(\d{4})_\d+$', name)
        if match:
            # Convert to title case and replace underscores with spaces
            title = match.group(1).replace('_', ' ').title()
            return f"{title} {int(match.group(2)):02d}"
            
        # Pattern 3: Clean up other names (remove numbers at end, extra spaces, etc.)
        name = re.sub(r'\d+$', '', name)  # Remove trailing numbers
        name = re.sub(r'[_-]+', ' ', name)  # Replace underscores/hyphens with spaces
        name = ' '.join(word for word in name.split() if not word.isdigit())  # Remove standalone numbers
        
        return name.strip() or "Untitled"

    async def _parse_ncx(self, zf: zipfile.ZipFile):
        """Parse the NCX file to get the table of contents"""
        try:
            if not self.ncx_path:
                return
                
            ncx_content = zf.read(self.ncx_path).decode('utf-8')
            soup = BeautifulSoup(ncx_content, 'xml')
            
            # Find all navPoints in the NCX
            nav_points = soup.find_all('navPoint')
            
            # Dictionary to store merged chapters
            chapter_groups = {}
            
            for i, nav_point in enumerate(nav_points):
                nav_label = nav_point.find('navLabel')
                content = nav_point.find('content')
                
                if not nav_label or not content:
                    continue
                    
                title = nav_label.get_text(strip=True)
                src = content.get('src', '')
                
                # Split the src into the ID reference and optional fragment
                src_parts = src.split('#')
                file_ref = src_parts[0]
                
                # Resolve the path relative to the NCX file
                file_path = self._resolve_path(self.ncx_path, file_ref)
                
                # Get the base filename for grouping
                filename = os.path.basename(file_path)
                
                # Get chapter key for grouping related files
                chapter_key = self._get_chapter_key(filename)
                
                # Get a nice display name for the chapter
                chapter_name = self._normalize_chapter_name(filename)
                
                # If we've seen this chapter before, add the file to the group
                if chapter_key in chapter_groups:
                    chapter_groups[chapter_key]['files'].append(file_path)
                else:
                    chapter_groups[chapter_key] = {
                        'title': chapter_name,
                        'files': [file_path],
                        'id': f'chapter_{len(chapter_groups) + 1}'
                    }
            
            # Convert the grouped chapters to the format expected by the rest of the code
            for chapter in chapter_groups.values():
                # Sort files to ensure consistent order (e.g., 0001_0000 comes before 0001_0001)
                chapter['files'].sort()
                
                self.toc.append({
                    'title': chapter['title'],
                    'file': chapter['files'][0],  # Use first file as the main chapter file
                    'additional_files': chapter['files'][1:],  # Store additional files for this chapter
                    'id': chapter['id']
                })
                
            # Sort chapters by their first file name for consistent ordering
            self.toc.sort(key=lambda x: x['file'])
            
        except Exception as e:
            print(f"Error parsing NCX: {e}")
            import traceback
            traceback.print_exc()

    async def _extract_text_from_html(self, content: bytes) -> str:
        """Extract clean text from HTML content"""
        try:
            # Decode content if it's bytes
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            
            # Clean up any encoding issues
            content = content.replace('\xad', '')  # Remove soft hyphens
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script, style, nav, header, footer elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'head', 'noscript']):
                element.decompose()
            
            # Get text with proper spacing
            text = soup.get_text('\n', strip=True)
            
            # Clean up the text
            text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
            text = '\n\n'.join(p for p in text.split('\n\n') if p.strip())
            
            return text if text.strip() else ""
            
        except Exception as e:
            print(f"Error in _extract_text_from_html: {e}")
            import traceback
            traceback.print_exc()
            return ""

    async def extract_text(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from EPUB with chapter information"""
        try:
            chapters = []
            
            with zipfile.ZipFile(file_path, 'r') as zf:
                print(f"Processing EPUB: {file_path}")
                print(f"Files in EPUB: {len(zf.namelist())}")
                
                # First, build a mapping of all HTML files by their base name
                html_files = {}
                for filename in zf.namelist():
                    if filename.lower().endswith(('.htm', '.html', '.xhtml')):
                        base_name = os.path.basename(filename)
                        html_files[base_name] = filename
                
                # Parse container to find OPF file
                container = zf.read(self.container_path).decode('utf-8')
                root = ET.fromstring(container)
                rootfile = root.find(".//{*}rootfile")
                if rootfile is None:
                    raise ValueError("Could not find rootfile in container.xml")
                
                self.opf_path = rootfile.get('full-path', '')
                self.root_dir = os.path.dirname(self.opf_path)
                
                # Parse OPF file
                opf_content = zf.read(self.opf_path).decode('utf-8')
                opf_root = ET.fromstring(opf_content)
                
                # Parse manifest
                manifest_elem = opf_root.find("{*}manifest")
                if manifest_elem is not None:
                    for item in manifest_elem.findall("{*}item"):
                        item_id = item.get('id', '')
                        href = item.get('href', '')
                        media_type = item.get('media-type', '')
                        
                        # Resolve the path relative to the OPF file
                        resolved_path = self._resolve_path(self.opf_path, href)
                        
                        self.manifest[item_id] = {
                            'href': resolved_path,
                            'media-type': media_type
                        }
                        self.id_to_href[item_id] = resolved_path
                        
                        # Check for NCX file (table of contents)
                        if media_type == 'application/x-dtbncx+xml':
                            self.ncx_path = resolved_path
                
                # Parse spine (reading order)
                spine_elem = opf_root.find("{*}spine")
                if spine_elem is not None:
                    self.spine = [itemref.get('idref', '') for itemref in spine_elem.findall("{*}itemref")]
                
                # Parse TOC if NCX file exists
                if self.ncx_path and self.ncx_path in zf.namelist():
                    await self._parse_ncx(zf)
                
                # Process chapters based on TOC
                if self.toc:
                    print(f"\nFound {len(self.toc)} chapters in TOC:")
                    print("-" * 50)
                    
                    for i, chapter in enumerate(self.toc, 1):
                        chapter_files = [chapter['file']] + chapter.get('additional_files', [])
                        chapter_content = []
                        
                        print(f"\nProcessing chapter {i}: {chapter['title']}")
                        
                        # Find all related files for this chapter
                        chapter_key = self._get_chapter_key(os.path.basename(chapter['file']))
                        related_files = [f for f in html_files.keys() 
                                      if self._get_chapter_key(f) == chapter_key]
                        
                        # Sort files to ensure consistent order
                        related_files.sort()
                        
                        print(f"Related files: {', '.join(related_files)}")
                        
                        for filename in related_files:
                            try:
                                content = zf.read(html_files[filename])
                                text = await self._extract_text_from_html(content)
                                if text:
                                    print(f"  - {filename}: {len(text)} characters")
                                    chapter_content.append(text)
                                else:
                                    print(f"  - {filename}: No text extracted")
                            except Exception as e:
                                print(f"  - Error processing {filename}: {str(e)}")
                        
                        if chapter_content:
                            full_content = '\n\n'.join(chapter_content)
                            print(f"  Total characters for chapter: {len(full_content)}")
                            print("-" * 50)
                            
                            chapters.append({
                                'title': chapter['title'],
                                'content': full_content,
                                'file': chapter['file']
                            })
                
                # If no TOC or no chapters found, fall back to spine items
                if not chapters and self.spine:
                    print("\nNo TOC found, falling back to spine items...")
                    for i, item_id in enumerate(self.spine, 1):
                        if item_id in self.manifest:
                            item = self.manifest[item_id]
                            item_path = item['href']
                            
                            if item_path in zf.namelist():
                                try:
                                    print(f"\nProcessing spine item {i}: {os.path.basename(item_path)}")
                                    content = zf.read(item_path)
                                    text = await self._extract_text_from_html(content)
                                    if text:
                                        print(f"  - {os.path.basename(item_path)}: {len(text)} characters")
                                        chapters.append({
                                            'title': f'Chapter {i:02d}',
                                            'content': text,
                                            'file': item_path
                                        })
                                    else:
                                        print(f"  - {os.path.basename(item_path)}: No text extracted")
                                except Exception as e:
                                    print(f"  - Error processing {os.path.basename(item_path)}: {str(e)}")
            
            print(f"\nSuccessfully extracted {len(chapters)} chapters with content")
            return chapters
            
        except Exception as e:
            print(f"\nError in extract_text: {e}")
            import traceback
            traceback.print_exc()
            raise Exception(f"Error extracting text from EPUB: {str(e)}")

    async def get_chapters(self, file_path: str) -> List[str]:
        """Get chapter titles from the EPUB"""
        try:
            chapters = await self.extract_text(file_path)
            return [chap.get('title', f'Capítulo {i+1}') for i, chap in enumerate(chapters)]
        except Exception as e:
            print(f"Error getting chapters: {e}")
            return []
    
    async def extract_chapter(self, file_path: str, chapter_index: int) -> Optional[str]:
        """Extract text for a specific chapter"""
        try:
            chapters = await self.extract_text(file_path)
            if 0 <= chapter_index < len(chapters):
                return chapters[chapter_index].get('content')
            return None
        except Exception as e:
            print(f"Error extracting chapter {chapter_index}: {e}")
            return None
    
    @classmethod
    def supports_file(cls, file_path: str) -> bool:
        """Check if the file is an EPUB"""
        return str(file_path).lower().endswith('.epub')
