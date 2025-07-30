import os
import re
import shutil
import tempfile
import zipfile
import rarfile
import patoolib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ColumnMergerService:
    """Service class for merging documents into a column-based format (OBITUARIES, SHOWERS, etc.)"""
    
    @staticmethod
    def extract_part_number(filename: str) -> int:
        """Extract part number from filename for sorting"""
        match = re.search(r'part(\d+)', filename.lower())
        return int(match.group(1)) if match else 0

    @staticmethod
    def sort_files_by_part(files: List[str]) -> List[str]:
        """Sort files by part number in filename"""
        return sorted(files, key=lambda f: ColumnMergerService.extract_part_number(os.path.basename(f)))

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
    def read_text_file(file_path: str) -> str:
        """Read text from a file, trying different encodings"""
        encodings = ['utf-8', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        # If all encodings fail, try binary mode and decode with errors='replace'
        with open(file_path, 'rb') as f:
            return f.read().decode('utf-8', errors='replace')

    @staticmethod
    def create_column_document(
        file_contents: List[Dict[str, str]], 
        output_path: str, 
        document_type: str = "OBITUARIES",
        date: Optional[str] = None
    ) -> None:
        """
        Create a document with content arranged in three columns
        
        Args:
            file_contents: List of dictionaries with filename and content
            output_path: Path to save the output PDF
            document_type: Type of document (OBITUARIES, SHOWERS, etc.)
            date: Date to display in the header (default: current date)
        """
        # Set up styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Heading1'],
            fontSize=12,
            alignment=1,  # center
        )
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading2'],
            fontSize=10,
            alignment=1,  # center
        )
        normal_style = ParagraphStyle(
            'Normal',
            parent=styles['Normal'],
            fontSize=8,
        )
        
        # Set up document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        # Create content
        content = []
        
        # Format date
        if not date:
            date = datetime.now().strftime("%B %d")
        
        # Create header
        filename = os.path.basename(output_path)
        header_data = [
            [Paragraph(document_type, header_style), 
             Paragraph(date, header_style), 
             Paragraph(filename, header_style)]
        ]
        header_table = Table(header_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        content.append(header_table)
        content.append(Spacer(1, 0.2*inch))
        
        # Create three columns for content
        num_files = len(file_contents)
        files_per_column = (num_files + 2) // 3  # Round up to ensure all content fits
        
        # Organize files into columns
        columns = [[], [], []]
        for i, file_dict in enumerate(file_contents):
            column_idx = min(i // files_per_column, 2)  # Ensure we don't exceed 3 columns
            columns[column_idx].append(file_dict)
        
        # Create content for each column
        column_content = []
        for column in columns:
            column_paragraphs = []
            for file_dict in column:
                # Add title (OBITUARY)
                entry_title = "OBITUARY" if document_type == "OBITUARIES" else "SHOWER"
                column_paragraphs.append(Paragraph(entry_title, title_style))
                
                # Add name (extracted from first line or filename)
                name = file_dict.get('name', os.path.basename(file_dict['filename']))
                column_paragraphs.append(Paragraph(name, title_style))
                
                # Add content
                paragraphs = file_dict['content'].split('\n')
                for p in paragraphs:
                    if p.strip():  # Skip empty lines
                        column_paragraphs.append(Paragraph(p, normal_style))
                
                column_paragraphs.append(Spacer(1, 0.1*inch))
            
            column_content.append(column_paragraphs)
        
        # Find the maximum number of elements in any column
        max_elements = max(len(column) for column in column_content)
        
        # Pad shorter columns with empty paragraphs
        for column in column_content:
            while len(column) < max_elements:
                column.append(Paragraph("", normal_style))
        
        # Create table with columns
        table_data = []
        for i in range(max_elements):
            row = []
            for column in column_content:
                if i < len(column):
                    row.append(column[i])
                else:
                    row.append(Paragraph("", normal_style))
            table_data.append(row)
        
        # Create table with columns
        column_table = Table(table_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
        column_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        content.append(column_table)
        
        # Build document
        doc.build(content)

    @staticmethod
    def extract_name_from_content(content: str) -> str:
        """Extract name from the first line of content"""
        lines = content.split('\n')
        for line in lines:
            if line.strip():
                return line.strip()
        return "Unknown"

    @staticmethod
    def merge_files_in_columns(
        archive_data: bytes, 
        output_filename: str, 
        temp_dir: str,
        document_type: str = "OBITUARIES",
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main method to merge files into a column-based format
        
        Args:
            archive_data: Bytes of the archive file
            output_filename: Name for the output file
            temp_dir: Temporary directory for processing
            document_type: Type of document (OBITUARIES, SHOWERS, etc.)
            date: Date to display in the header (default: current date)
            
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
        extracted = ColumnMergerService.extract_compressed_file(temp_path, extract_dir)

        # Filter for text files
        valid_exts = ['.txt', '.md', '.text']
        filtered = ColumnMergerService.filter_files_by_extension(extracted, valid_exts)
        if not filtered:
            raise Exception("No valid text files found.")

        # Sort files by part number
        sorted_files = ColumnMergerService.sort_files_by_part(filtered)
        
        # Read file contents
        file_contents = []
        for file_path in sorted_files:
            content = ColumnMergerService.read_text_file(file_path)
            name = ColumnMergerService.extract_name_from_content(content)
            file_contents.append({
                'filename': os.path.basename(file_path),
                'content': content,
                'name': name
            })
        
        # Create output path
        output_path = os.path.join(temp_dir, f"{output_filename}.pdf")
        
        # Create column-based document
        ColumnMergerService.create_column_document(
            file_contents=file_contents,
            output_path=output_path,
            document_type=document_type,
            date=date
        )
        
        return {
            "output_path": output_path,
            "filename": f"{output_filename}.pdf",
            "media_type": "application/pdf"
        }
