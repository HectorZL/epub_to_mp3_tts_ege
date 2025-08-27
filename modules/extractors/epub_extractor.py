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

    def _extract_chapter_number(self, filename: str) -> int:
        """Extract chapter number from filename for sorting"""
        # Try to extract number from patterns like 0001_0000 or _0001_
        match = re.search(r'(?:^|_)(\d{4})(?:_|$)', filename)
        if match:
            return int(match.group(1))
        # For files without numbers, put them at the end
        return 9999

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

    async def _get_toc_from_html_files(self, html_files):
        """Create a TOC by scanning all HTML files directly"""
        toc = []
        for i, html_file in enumerate(sorted(html_files), 1):
            toc.append({
                'title': f"Chapter {i:03d}",
                'file': html_file,
                'additional_files': [],
                'id': f'chapter_{i:03d}'
            })
        return toc

    async def _extract_text_from_html(self, content: bytes) -> str:
        """Extract clean text from HTML content while preserving all meaningful content"""
        try:
            # Decode content if it's bytes
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            
            # Initial cleanup of problematic patterns that could lead to repeated characters
            content = re.sub(r'\s*[=_-]+\s*', ' ', content)  # Clean up separators with spaces
            content = re.sub(r'\s{2,}', ' ', content)  # Normalize spaces
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script, style, and other non-content elements
            for element in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'button', 'input', 'select', 'textarea']):
                element.decompose()
            
            # Process text content
            text = soup.get_text(' ', strip=True)
            
            # Clean up the extracted text
            lines = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                    
                # Skip lines that are just separators or special characters
                if re.fullmatch(r'^[=_-]{2,}$', line) or re.fullmatch(r'^[\W_]+$', line):
                    continue
                    
                # Skip lines with too many repeated characters
                if re.search(r'(.)\1{3,}', line):
                    continue
                    
                # Clean up the line
                line = re.sub(r'\s*[=_-]+\s*', ' ', line)  # Remove separators
                line = re.sub(r'\s{2,}', ' ', line)  # Normalize spaces
                
                lines.append(line)
            
            # Combine lines and clean up
            cleaned_text = ' '.join(lines)
            cleaned_text = re.sub(r'\s*([.,;:!?])\s*', r'\1 ', cleaned_text)  # Fix punctuation spacing
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()  # Final cleanup
            
            return cleaned_text
            
        except Exception as e:
            print(f"Error extracting text from HTML: {e}")
            return ""

    async def extract_text(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract text from EPUB with chapter information"""
        try:
            chapters = []
            
            with zipfile.ZipFile(file_path, 'r') as zf:
                print(f"Processing EPUB: {file_path}")
                print(f"Files in EPUB: {len(zf.namelist())}")
                
                # Get all HTML files first
                html_files = [f for f in zf.namelist() if f.lower().endswith(('.htm', '.html', '.xhtml'))]
                print(f"Found {len(html_files)} HTML files in EPUB")
                
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
                self.manifest = {}
                manifest_elem = opf_root.find("{*}manifest")
                if manifest_elem is not None:
                    for item in manifest_elem.findall("{*}item"):
                        item_id = item.get('id', '')
                        href = item.get('href', '')
                        media_type = item.get('media-type', '')
                        
                        resolved_path = self._resolve_path(self.opf_path, href)
                        self.manifest[item_id] = {
                            'href': resolved_path,
                            'media-type': media_type
                        }
                        self.id_to_href[item_id] = resolved_path
                        
                        if media_type == 'application/x-dtbncx+xml':
                            self.ncx_path = resolved_path
                
                # Parse spine (reading order)
                self.spine = []
                spine_elem = opf_root.find("{*}spine")
                if spine_elem is not None:
                    self.spine = [itemref.get('idref', '') for itemref in spine_elem.findall("{*}itemref")]
                
                # Method 1: Get TOC from NCX
                ncx_toc = []
                if self.ncx_path and self.ncx_path in zf.namelist():
                    original_toc = self.toc
                    await self._parse_ncx(zf)
                    ncx_toc = self.toc.copy()
                    self.toc = original_toc  # Reset to avoid side effects
                
                # Method 2: Get TOC from spine
                spine_toc = []
                if self.spine:
                    spine_toc = [{
                        'title': f"Chapter {i+1:03d}",
                        'file': self.id_to_href[item_id],
                        'additional_files': [],
                        'id': f'chapter_{i+1:03d}'
                    } for i, item_id in enumerate(self.spine) if item_id in self.id_to_href]
                
                # Method 3: Get TOC from all HTML files
                html_toc = await self._get_toc_from_html_files(html_files)
                
                # Choose the TOC with the most chapters, but prefer Spine TOC if available
                possible_tocs = [
                    ("Spine TOC", spine_toc) if spine_toc else None,
                    ("NCX TOC", ncx_toc) if ncx_toc else None,
                    ("HTML Files TOC", html_toc) if html_toc else None
                ]
                
                # Filter out None values and sort by length
                valid_tocs = [toc for toc in possible_tocs if toc is not None]
                if not valid_tocs:
                    raise ValueError("No valid TOC found in the EPUB")
                
                # Sort by number of chapters (descending)
                valid_tocs.sort(key=lambda x: len(x[1]), reverse=True)
                
                # If we have multiple TOCs with the same number of chapters, prefer Spine > NCX > HTML
                if len(valid_tocs) > 1 and len(valid_tocs[0][1]) == len(valid_tocs[1][1]):
                    preferred_order = ["Spine TOC", "NCX TOC", "HTML Files TOC"]
                    valid_tocs.sort(key=lambda x: preferred_order.index(x[0]) if x[0] in preferred_order else 999)
                
                selected_name, self.toc = valid_tocs[0]
                
                print(f"\nTOC Selection Results:")
                print(f"- NCX TOC: {len(ncx_toc)} chapters" if ncx_toc else "- NCX TOC: Not available")
                print(f"- Spine TOC: {len(spine_toc)} chapters" if spine_toc else "- Spine TOC: Not available")
                print(f"- HTML Files TOC: {len(html_toc)} chapters" if html_toc else "- HTML Files TOC: Not available")
                print(f"\nSelected {selected_name} with {len(self.toc)} chapters")
                
                # Process all chapters from the selected TOC
                print("\n" + "="*50)
                print(f"PROCESSING {len(self.toc)} CHAPTERS")
                print("="*50)
                
                chapters = []
                for i, chapter in enumerate(self.toc, 1):
                    print(f"\nProcessing chapter {i:03d}/{len(self.toc)}: {chapter['title']}")
                    print(f"File: {chapter['file']}")
                    
                    chapter_files = [chapter['file']] + chapter.get('additional_files', [])
                    chapter_content = []
                    
                    for file_path in chapter_files:
                        if file_path not in zf.namelist():
                            print(f"  - Warning: File not found: {file_path}")
                            continue
                            
                        try:
                            content = zf.read(file_path)
                            text = await self._extract_text_from_html(content)
                            if text:
                                print(f"  - Extracted: {len(text)} characters")
                                chapter_content.append(text)
                            else:
                                print("  - No text extracted")
                        except Exception as e:
                            print(f"  - Error processing {file_path}: {str(e)}")
                    
                    full_content = '\n\n'.join(chapter_content) if chapter_content else ""
                    chapters.append({
                        'title': chapter['title'],
                        'content': full_content,
                        'file': chapter['file']
                    })
                
                print("\n" + "="*50)
                print(f"COMPLETED PROCESSING {len(chapters)} CHAPTERS")
                print("="*50)
                
                return chapters
                
        except Exception as e:
            print(f"\nERROR processing EPUB: {e}")
            import traceback
            traceback.print_exc()
            return []
    
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
