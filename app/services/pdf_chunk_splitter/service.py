import os
import zipfile
from typing import Any, Dict, List

from PyPDF2 import PdfReader, PdfWriter


class PDFChunkSplitterService:
    """Service class for splitting PDF files into chunks of N pages"""

    @staticmethod
    def split_by_chunk_size(pdf_path: str, output_folder: str, chunk_size: int) -> Dict[str, Any]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")

        print(f"Starting PDF chunk splitting process for: {pdf_path}")
        print(f"Output folder: {output_folder}")
        print(f"Chunk size: {chunk_size}")

        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        print(f"Base name: {base_name}")

        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        print(f"Total pages in PDF: {total_pages}")

        output_files: List[str] = []

        for i in range(0, total_pages, chunk_size):
            writer = PdfWriter()

            end_page = min(i + chunk_size, total_pages)
            for page_num in range(i, end_page):
                writer.add_page(reader.pages[page_num])

            part_number = (i // chunk_size) + 1
            output_filename = f"{base_name}_Part{part_number}.pdf"
            output_file = os.path.join(output_folder, output_filename)
            print(f"Creating part {part_number} (pages {i+1}-{end_page}): {output_file}")

            with open(output_file, "wb") as output_pdf:
                writer.write(output_pdf)

            if os.path.exists(output_file):
                print(f"Successfully created: {output_file}")
                output_files.append(output_file)
            else:
                print(f"Failed to create: {output_file}")

        zip_filename = f"{base_name}_chunk_split.zip"
        zip_path = os.path.join(output_folder, zip_filename)
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for path in output_files:
                zipf.write(path, os.path.basename(path))

        print(f"PDF chunk splitting complete. Created {len(output_files)} files and zipped them.")
        return {
            "output_files": output_files,
            "zip_path": zip_path,
            "zip_filename": zip_filename,
            "chunk_size": chunk_size,
            "total_chunks": len(output_files),
        }
