import os
import io
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("agent.core.file_extractor")

# Supported file categories
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx", ".doc"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".xml", ".html", ".css", ".js", ".jsx", ".ts", ".tsx", ".py", ".java",
    ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".sql", ".sh", ".bat", ".ps1",
    ".ini", ".cfg", ".conf", ".log", ".env"
}


def get_file_type_label(extension: str) -> str:
    ext = extension.lower()
    if ext in PDF_EXTENSIONS:
        return "pdf"
    elif ext in DOCX_EXTENSIONS:
        return "docx"
    elif ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    else:
        return f"{round(size_bytes / (1024 * 1024), 1)} MB"


def extract_pdf_text(file_bytes_or_path: Any, max_pages: int = 50, max_chars: int = 100000) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts text and page metadata from a PDF file or bytes using pypdf.
    """
    metadata: Dict[str, Any] = {"page_count": 0, "title": "", "author": ""}
    extracted_text_parts: List[str] = []
    
    try:
        from pypdf import PdfReader
        if isinstance(file_bytes_or_path, (bytes, bytearray)):
            stream = io.BytesIO(file_bytes_or_path)
            reader = PdfReader(stream)
        else:
            reader = PdfReader(str(file_bytes_or_path))
            
        num_pages = len(reader.pages)
        metadata["page_count"] = num_pages
        if reader.metadata:
            metadata["title"] = reader.metadata.title or ""
            metadata["author"] = reader.metadata.author or ""
            
        pages_to_read = min(num_pages, max_pages)
        for i in range(pages_to_read):
            page = reader.pages[i]
            page_text = page.extract_text() or ""
            extracted_text_parts.append(f"--- Page {i + 1} ---\n{page_text.strip()}")
            if sum(len(p) for p in extracted_text_parts) > max_chars:
                extracted_text_parts.append("\n[Content truncated due to length...]")
                break
                
        full_text = "\n\n".join(extracted_text_parts).strip()
        return full_text, metadata
    except Exception as e:
        logger.warning(f"Error parsing PDF: {e}")
        return f"[PDF parsing error or scanned document: {str(e)}]", metadata


def extract_docx_text(file_bytes_or_path: Any, max_paragraphs: int = 500) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts text paragraphs and tables from a Word (.docx) document using python-docx.
    """
    metadata: Dict[str, Any] = {"paragraphs": 0, "tables": 0}
    text_parts: List[str] = []
    
    try:
        import docx
        if isinstance(file_bytes_or_path, (bytes, bytearray)):
            stream = io.BytesIO(file_bytes_or_path)
            doc = docx.Document(stream)
        else:
            doc = docx.Document(str(file_bytes_or_path))
            
        # Extract paragraphs
        for p in doc.paragraphs[:max_paragraphs]:
            if p.text.strip():
                text_parts.append(p.text.strip())
        metadata["paragraphs"] = len(doc.paragraphs)
        
        # Extract tables
        metadata["tables"] = len(doc.tables)
        for i, table in enumerate(doc.tables[:10]):
            table_rows: List[str] = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                table_rows.append(" | ".join(cells))
            if table_rows:
                text_parts.append(f"\n[Table {i + 1}]\n" + "\n".join(table_rows))
                
        full_text = "\n\n".join(text_parts).strip()
        return full_text, metadata
    except Exception as e:
        logger.warning(f"Error parsing DOCX: {e}")
        return f"[DOCX parsing error: {str(e)}]", metadata


def extract_image_info(file_bytes_or_path: Any) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """
    Extracts dimensions, format, and base64 string for an image.
    """
    metadata: Dict[str, Any] = {"format": "JPEG", "width": 0, "height": 0}
    base64_str: Optional[str] = None
    
    try:
        from PIL import Image
        if isinstance(file_bytes_or_path, (bytes, bytearray)):
            data = file_bytes_or_path
            img = Image.open(io.BytesIO(data))
        else:
            with open(str(file_bytes_or_path), "rb") as f:
                data = f.read()
            img = Image.open(str(file_bytes_or_path))
            
        metadata["format"] = img.format or "JPEG"
        metadata["width"], metadata["height"] = img.size
        
        # Ensure image is in a standard format for API transmission
        if metadata["format"].upper() in ["JPEG", "JPG", "PNG", "WEBP"]:
            base64_str = base64.b64encode(data).decode("utf-8")
        else:
            # Convert to PNG in memory
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            base64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            metadata["format"] = "PNG"
            
        summary = f"[Image: {metadata['format']}, {metadata['width']}x{metadata['height']} pixels]"
        return summary, base64_str, metadata
    except Exception as e:
        logger.warning(f"Error processing image: {e}")
        return f"[Image processing error: {str(e)}]", None, metadata


def extract_text_file(file_bytes_or_path: Any, max_chars: int = 100000) -> Tuple[str, Dict[str, Any]]:
    """
    Reads plain text/code/markdown/json/csv files with UTF-8 fallback.
    """
    metadata: Dict[str, Any] = {"line_count": 0}
    try:
        if isinstance(file_bytes_or_path, (bytes, bytearray)):
            try:
                raw_text = file_bytes_or_path.decode("utf-8")
            except UnicodeDecodeError:
                raw_text = file_bytes_or_path.decode("latin-1", errors="ignore")
        else:
            with open(str(file_bytes_or_path), "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
                
        lines = raw_text.splitlines()
        metadata["line_count"] = len(lines)
        if len(raw_text) > max_chars:
            raw_text = raw_text[:max_chars] + "\n\n[Content truncated due to size...]"
        return raw_text, metadata
    except Exception as e:
        return f"[Text file read error: {str(e)}]", metadata


def process_uploaded_file(filename: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Universal processing pipeline for any uploaded file (PDF, DOC/DOCX, Image, Text, Code, Binary).
    Returns a unified attachment context object.
    """
    ext = os.path.splitext(filename)[1].lower()
    file_type = get_file_type_label(ext)
    size_bytes = len(file_bytes)
    size_str = format_size(size_bytes)
    
    extracted_text = ""
    image_base64 = None
    metadata: Dict[str, Any] = {}
    is_image = False
    
    if file_type == "pdf":
        extracted_text, metadata = extract_pdf_text(file_bytes)
    elif file_type == "docx":
        extracted_text, metadata = extract_docx_text(file_bytes)
    elif file_type == "image":
        is_image = True
        summary, image_base64, metadata = extract_image_info(file_bytes)
        extracted_text = summary
    elif file_type == "text":
        extracted_text, metadata = extract_text_file(file_bytes)
    else:
        # Unknown/binary fallback
        extracted_text = f"[Binary file: {filename} ({size_str}) - Content cannot be directly converted to text]"
        metadata = {"binary": True}

    return {
        "id": f"att_{int(os.times().elapsed * 1000)}_{os.urandom(4).hex()}",
        "filename": filename,
        "extension": ext,
        "file_type": file_type,
        "size_bytes": size_bytes,
        "size_str": size_str,
        "extracted_text": extracted_text,
        "image_base64": image_base64,
        "is_image": is_image,
        "metadata": metadata
    }
