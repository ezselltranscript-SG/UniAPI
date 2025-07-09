import os
import zipfile
from typing import Dict, Any, List
from PyPDF2 import PdfReader, PdfWriter

class PDFCustomSplitterService:
    """Service class for splitting PDF files into custom page groups"""
    
    @staticmethod
    def split_by_page_count(pdf_path: str, output_folder: str, pages_per_file: int) -> Dict[str, Any]:
        """Split a PDF file into groups with a specified number of pages per output file.

        Args:
            pdf_path: Path to the PDF file
            output_folder: Folder to save the split pages
            pages_per_file: Number of pages per output file

        Returns:
            Dictionary with output files list and zip file path
        """
        print(f"Starting PDF custom splitting process for: {pdf_path}")
        print(f"Output folder: {output_folder}")
        print(f"Pages per file: {pages_per_file}")
        
        # Get the base name of the PDF file without extension
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        print(f"Base name: {base_name}")
        
        # Read the PDF file
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"Total pages in PDF: {total_pages}")
        
        output_files = []
        
        # Process pages in groups of pages_per_file
        for i in range(0, total_pages, pages_per_file):
            # Create a PDF writer for the current group of pages
            writer = PdfWriter()
            
            # Add pages to the current group
            end_page = min(i + pages_per_file, total_pages)
            for page_num in range(i, end_page):
                writer.add_page(reader.pages[page_num])
            
            # Define the output file path
            group_number = (i // pages_per_file) + 1
            start_page = i + 1
            output_filename = f"{base_name}_Group{group_number}_Pages{start_page}-{end_page}.pdf"
            output_file = os.path.join(output_folder, output_filename)
            print(f"Creating group {group_number} (pages {start_page}-{end_page}): {output_file}")
            
            # Write the pages to a new PDF file
            with open(output_file, "wb") as output_pdf:
                writer.write(output_pdf)
            
            # Verify the file was created
            if os.path.exists(output_file):
                print(f"Successfully created: {output_file}")
                output_files.append(output_file)
            else:
                print(f"Failed to create: {output_file}")
        
        # Create ZIP file
        zip_filename = f"{base_name}_custom_split.zip"
        zip_path = os.path.join(output_folder, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path in output_files:
                zipf.write(path, os.path.basename(path))
        
        print(f"PDF custom splitting complete. Created {len(output_files)} files and zipped them.")
        return {
            "output_files": output_files,
            "zip_path": zip_path,
            "zip_filename": zip_filename,
            "pages_per_file": pages_per_file,
            "total_groups": len(output_files)
        }
