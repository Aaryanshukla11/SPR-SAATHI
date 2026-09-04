import io
import os
import pytest
from PIL import Image
from agent.core.file_extractor import (
    process_uploaded_file,
    extract_pdf_text,
    extract_docx_text,
    extract_image_info,
    extract_text_file,
    get_file_type_label,
    format_size
)

def test_file_type_classification():
    assert get_file_type_label(".pdf") == "pdf"
    assert get_file_type_label(".docx") == "docx"
    assert get_file_type_label(".doc") == "docx"
    assert get_file_type_label(".png") == "image"
    assert get_file_type_label(".jpg") == "image"
    assert get_file_type_label(".txt") == "text"
    assert get_file_type_label(".py") == "text"
    assert get_file_type_label(".bin") == "binary"

def test_format_size():
    assert format_size(500) == "500 B"
    assert "KB" in format_size(2048)
    assert "MB" in format_size(1024 * 1024 * 3)

def test_text_file_extraction():
    content = "Function hello():\n    return 'world'".encode("utf-8")
    item = process_uploaded_file("script.py", content)
    assert item["filename"] == "script.py"
    assert item["file_type"] == "text"
    assert "Function hello()" in item["extracted_text"]
    assert item["metadata"]["line_count"] == 2

def test_image_extraction():
    buf = io.BytesIO()
    img = Image.new("RGB", (64, 64), color="red")
    img.save(buf, format="PNG")
    data = buf.getvalue()
    
    item = process_uploaded_file("test.png", data)
    assert item["filename"] == "test.png"
    assert item["file_type"] == "image"
    assert item["is_image"] is True
    assert item["image_base64"] is not None
    assert item["metadata"]["width"] == 64
    assert item["metadata"]["height"] == 64

def test_docx_empty_or_mock():
    # Test handling of non-docx data gracefully
    text, meta = extract_docx_text(b"corrupt data")
    assert "error" in text.lower() or text == ""
