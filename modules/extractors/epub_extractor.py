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
    
    async def _parse_ncx(self, zf: zipfile.ZipFile):
        """Parse the NCX file to get the table of contents"""
        try:
            if not self.ncx_path:
                return
                
            ncx_content = zf.read(self.ncx_path).decode('utf-8')
            soup = BeautifulSoup(ncx_content, 'xml')
            
            # Find all navPoints in the NCX
            nav_points = soup.find_all('navPoint')
            
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
                
                self.toc.append({
                    'title': title or f'Capítulo {i+1}',
                    'file': file_path,
                    'id': f'chapter_{i+1}'
                })
                
        except Exception as e:
            print(f"Error parsing NCX: {e}")
    
    async def _extract_text_from_html(self, content: bytes) -> str:
        """Extract clean text from HTML content"""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text and clean it up
            text = soup.get_text(separator='\n', strip=True)
            # Remove excessive whitespace
            text = '\n'.join(line.strip() for line in text.splitlines() if line.strip())
            return text
            
        except Exception as e:
            print(f"Error extracting text from HTML: {e}")
            return ""
    
    async def extract_text(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from EPUB with chapter information
        
        Returns:
            List of dictionaries containing 'title' and 'content' for each chapter
        """
        try:
            chapters = []
            
            with zipfile.ZipFile(file_path, 'r') as zf:
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
                    for itemref in spine_elem.findall("{*}itemref"):
                        idref = itemref.get('idref', '')
                        if idref in self.manifest:
                            self.spine.append(idref)
                
                # Parse TOC if NCX file exists
                if self.ncx_path and self.ncx_path in zf.namelist():
                    await self._parse_ncx(zf)
                
                # Process chapters based on TOC or spine
                if self.toc:
                    # Use TOC for chapter structure
                    for i, chapter in enumerate(self.toc):
                        chapter_file = chapter.get('file', '')
                        if chapter_file and chapter_file in zf.namelist():
                            try:
                                content = zf.read(chapter_file)
                                text = await self._extract_text_from_html(content)
                                if text:
                                    chapters.append({
                                        'title': chapter.get('title', f'Capítulo {i+1}'),
                                        'content': text,
                                        'file': chapter_file
                                    })
                            except Exception as e:
                                print(f"Error processing chapter {chapter.get('title')}: {e}")
                
                # If no TOC or no chapters found, use spine items as chapters
                if not chapters and self.spine:
                    for i, item_id in enumerate(self.spine):
                        if item_id in self.manifest:
                            item = self.manifest[item_id]
                            item_path = item['href']
                            
                            if item_path in zf.namelist():
                                try:
                                    content = zf.read(item_path)
                                    text = await self._extract_text_from_html(content)
                                    if text:
                                        chapters.append({
                                            'title': f'Capítulo {i+1}',
                                            'content': text,
                                            'file': item_path
                                        })
                                except Exception as e:
                                    print(f"Error processing spine item {item_id}: {e}")
            
            return chapters
            
        except Exception as e:
            print(f"Error in extract_text: {e}")
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
