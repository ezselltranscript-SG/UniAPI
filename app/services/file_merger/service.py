import os
import re
import shutil
import tempfile
import zipfile
import rarfile
import patoolib
import logging
from typing import List, Dict, Any, Optional
from pypdf import PdfWriter, PdfReader
from docx import Document
from docxcompose.composer import Composer
from docx.enum.text import WD_BREAK

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileMergerService:
    """Service class for merging PDF and DOCX files"""
    
    @staticmethod
    def extract_part_number(filename: str) -> int:
        """Extract part number from filename for sorting"""
        match = re.search(r'part(\d+)', filename.lower())
        return int(match.group(1)) if match else 0

    @staticmethod
    def sort_files_by_part(files: List[str]) -> List[str]:
        """Sort files by part number in filename"""
        return sorted(files, key=lambda f: FileMergerService.extract_part_number(os.path.basename(f)))

    @staticmethod
    def extract_compressed_file(file_path: str, extract_dir: str) -> List[str]:
        """Extract files from compressed archive (zip, rar, etc.)"""
        extracted_files = []
        
        # Try ZIP format
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                return [os.path.join(extract_dir, name) for name in zip_ref.namelist() if not name.endswith('/')]
        except zipfile.BadZipFile:
            pass

        # Try RAR format
        try:
            rarfile.UNRAR_TOOL = 'unrar'
            with rarfile.RarFile(file_path) as rar_ref:
                rar_ref.extractall(extract_dir)
                return [os.path.join(extract_dir, name) for name in rar_ref.namelist() if not rar_ref.getinfo(name).isdir()]
        except rarfile.NotRarFile:
            pass

        # Try other formats using patool
        try:
            patoolib.extract_archive(file_path, outdir=extract_dir)
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    extracted_files.append(os.path.join(root, file))
            return extracted_files
        except Exception as e:
            logger.error(f"Error extracting archive: {str(e)}")
            raise Exception(f"Error extracting archive: {str(e)}")

    @staticmethod
    def filter_files_by_extension(file_paths: List[str], extensions: List[str]) -> List[str]:
        """Filter files by extension"""
        return [p for p in file_paths if os.path.splitext(p)[1].lower() in extensions]

    @staticmethod
    def merge_pdf_files(file_paths: List[str], output_path: str) -> None:
        """Merge multiple PDF files into one"""
        merger = PdfWriter()
        for path in file_paths:
            reader = PdfReader(path)
            for page in reader.pages:
                merger.add_page(page)
        with open(output_path, "wb") as out:
            merger.write(out)

    @staticmethod
    def merge_docx_simple(file_paths: List[str], output_path: str) -> None:
        """
        Merge multiple DOCX files into one.
        Each document is inserted as a new section with its own header
        and starts on a new page.
        """
        if not file_paths:
            raise Exception("No DOCX files provided")
        
        if len(file_paths) == 1:
            # If there's only one file, just copy it
            shutil.copy(file_paths[0], output_path)
            return
        
        try:
            # Create a base document with the first file
            master = Document(file_paths[0])
            composer = Composer(master)
            
            # Add each additional document with a page break before
            for i, file_path in enumerate(file_paths[1:], 1):
                logger.info(f"Adding document {i}: {os.path.basename(file_path)}")
                doc = Document(file_path)
                
                # Add a page break before each document
                # First add an empty paragraph to the main document
                p = master.add_paragraph()
                run = p.add_run()
                run.add_break(WD_BREAK.PAGE)
                
                # Create a new section for each document
                # This can help preserve headers
                section = master.add_section()
                
                # Then add the document
                composer.append(doc)
            
            # Save the combined document
            composer.save(output_path)
            logger.info(f"Combined document saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Error merging documents: {str(e)}")
            raise Exception(f"Error merging documents: {str(e)}")
    
    @staticmethod
    def merge_files(archive_data: bytes, output_filename: str, temp_dir: str) -> Dict[str, Any]:
        """
        Main method to merge files from an archive
        
        Args:
            archive_data: Bytes of the archive file
            output_filename: Name for the output file
            temp_dir: Temporary directory for processing
            
        Returns:
            Dictionary with output path and media type
        """
        # Save the uploaded archive to a temporary file
        temp_path = os.path.join(temp_dir, "archive_input")
        with open(temp_path, "wb") as f:
            f.write(archive_data)

        # Extract the archive
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        extracted = FileMergerService.extract_compressed_file(temp_path, extract_dir)

        # Filter for PDF and DOCX files
        valid_exts = ['.pdf', '.docx']
        filtered = FileMergerService.filter_files_by_extension(extracted, valid_exts)
        if not filtered:
            raise Exception("No valid PDF or DOCX files found.")

        # Sort files by part number
        sorted_files = FileMergerService.sort_files_by_part(filtered)
        
        # Determine the output file type based on the first file
        ext = os.path.splitext(sorted_files[0])[1].lower()
        output_path = os.path.join(temp_dir, f"{output_filename}{ext}")

        # Merge files based on type
        if ext == ".pdf":
            FileMergerService.merge_pdf_files(sorted_files, output_path)
            media_type = "application/pdf"
        elif ext == ".docx":
            FileMergerService.merge_docx_simple(sorted_files, output_path)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise Exception("Unsupported file type.")

        return {
            "output_path": output_path,
            "filename": f"{output_filename}{ext}",
            "media_type": media_type
        }
