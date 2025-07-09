import os
import shutil
import zipfile
from typing import List, Dict, Any
from PyPDF2 import PdfReader, PdfWriter

class PDFPairSplitterService:
    """Service class for splitting PDF files into pairs of pages"""
    
    @staticmethod
    def split_page_pairs(pdf_path: str, output_folder: str) -> Dict[str, Any]:
        """Split a PDF file into pairs of pages (2 pages per output file).

        Args:
            pdf_path: Path to the PDF file
            output_folder: Folder to save the split pages

        Returns:
            Dictionary with output files list and zip file path
        """
        print(f"Starting PDF pair splitting process for: {pdf_path}")
        print(f"Output folder: {output_folder}")
        
        # Get the base name of the PDF file without extension
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        print(f"Base name: {base_name}")
        
        # Read the PDF file
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"Total pages in PDF: {total_pages}")
        
        output_files = []
        
        # Process pages in pairs
        for i in range(0, total_pages, 2):
            # Create a PDF writer for the current pair of pages
            writer = PdfWriter()
            
            # Add the first page of the pair
            writer.add_page(reader.pages[i])
            
            # Add the second page if it exists
            if i + 1 < total_pages:
                writer.add_page(reader.pages[i + 1])
            
            # Define the output file path
            part_number = (i // 2) + 1
            output_filename = f"{base_name}_Part{part_number}.pdf"
            output_file = os.path.join(output_folder, output_filename)
            print(f"Creating part {part_number} (pages {i+1}-{min(i+2, total_pages)}): {output_file}")
            
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
        zip_filename = f"{base_name}_split.zip"
        zip_path = os.path.join(output_folder, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for path in output_files:
                zipf.write(path, os.path.basename(path))
        
        print(f"PDF pair splitting complete. Created {len(output_files)} files and zipped them.")
        return {
            "output_files": output_files,
            "zip_path": zip_path,
            "zip_filename": zip_filename
        }
