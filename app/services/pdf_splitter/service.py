import os
import shutil
from typing import List
from PyPDF2 import PdfReader, PdfWriter

class PDFSplitterService:
    """Service class for PDF splitting operations"""
    
    @staticmethod
    def split_pages(pdf_path: str, output_folder: str) -> List[str]:
        """Split a PDF file into individual pages.

        Args:
            pdf_path: Path to the PDF file
            output_folder: Folder to save the split pages

        Returns:
            List of paths to the split PDF files
        """
        print(f"Starting PDF splitting process for: {pdf_path}")
        print(f"Output folder: {output_folder}")
        
        # Get the base name of the PDF file without extension
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        print(f"Base name: {base_name}")
        
        # Read the PDF file
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"Total pages in PDF: {total_pages}")
        
        output_files = []
        
        # Process each page
        for i in range(total_pages):
            # Create a PDF writer for the current page
            writer = PdfWriter()
            writer.add_page(reader.pages[i])
            
            # Define the output file path
            output_file = os.path.join(output_folder, f"{base_name}-Part{i+1}.pdf")
            print(f"Creating page {i+1}/{total_pages}: {output_file}")
            
            # Write the page to a new PDF file
            with open(output_file, "wb") as output_pdf:
                writer.write(output_pdf)
            
            # Verify the file was created
            if os.path.exists(output_file):
                print(f"Successfully created: {output_file}")
                output_files.append(output_file)
            else:
                print(f"Failed to create: {output_file}")
        
        print(f"PDF splitting complete. Created {len(output_files)} files.")
        return output_files
