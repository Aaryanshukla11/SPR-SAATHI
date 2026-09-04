import pytest
import os

from agent.core.productivity import (
    SpreadsheetManager, DocumentManager, PresentationManager
)


# ============================================================================
# 1. EXCEL / SPREADSHEET TESTS (Create, Modify, Analyze, Validate)
# ============================================================================

def test_spreadsheet_lifecycle_and_analysis(tmp_path):
    """Verify spreadsheet creation, modification, statistical analysis, and validation."""
    sheet_path = tmp_path / "quarterly_finances.csv"

    headers = ["Department", "Budget", "Spent"]
    rows = [
        ["Engineering", "500000", "420000"],
        ["Marketing", "200000", "195000"],
        ["Sales", "300000", "280000"]
    ]
    formulas = {
        "Department": "TOTAL",
        "Budget": "=SUM(B2:B4)",
        "Spent": "=SUM(C2:C4)"
    }

    # 1. Create
    res_create = SpreadsheetManager.create_spreadsheet(str(sheet_path), headers, rows, formulas)
    assert os.path.exists(sheet_path)
    assert res_create["row_count"] == 4  # 3 rows + 1 formula row

    # 2. Reopen & Read
    res_read = SpreadsheetManager.read_spreadsheet(str(sheet_path))
    assert res_read["headers"] == headers
    assert len(res_read["rows"]) == 4

    # 3. Analyze Data
    analysis = SpreadsheetManager.analyze_spreadsheet(str(sheet_path))
    assert "Budget" in analysis["columns"]
    assert analysis["columns"]["Budget"]["sum"] == 1000000.0
    assert analysis["columns"]["Budget"]["mean"] == round(1000000.0 / 3, 2)

    # 4. Modify (append new row)
    res_mod = SpreadsheetManager.modify_spreadsheet(
        str(sheet_path),
        append_rows=[["Operations", "150000", "140000"]]
    )
    assert res_mod["modified"] is True
    assert res_mod["new_row_count"] == 5

    # 5. Validate Output
    is_valid = SpreadsheetManager.validate_spreadsheet(str(sheet_path), min_rows=5, required_headers=["Budget", "Spent"])
    assert is_valid is True


# ============================================================================
# 2. WORD / DOCUMENT TESTS (Create, Edit, Extract, Validate)
# ============================================================================

def test_document_lifecycle_and_extraction(tmp_path):
    """Verify document creation, section editing, text replacement, and word extraction."""
    doc_path = tmp_path / "Project_Charter.md"

    title = "SPR SAATHI System Architecture"
    sections = [
        {"heading": "Executive Summary", "content": "Autonomous Windows desktop agent with rich multimodal intelligence."},
        {"heading": "Core Tenets", "content": "1. Reliability\n2. Deterministic Verification\n3. Bounded Safety"}
    ]

    # 1. Create
    res_create = DocumentManager.create_document(str(doc_path), title, sections, author="AI Agent")
    assert os.path.exists(doc_path)
    assert res_create["sections_count"] == 2

    # 2. Reopen & Read
    data = DocumentManager.read_document(str(doc_path))
    assert title in data["text"]
    assert len(data["headings"]) >= 2
    assert data["word_count"] > 10

    # 3. Modify (append section and replace text)
    res_mod = DocumentManager.modify_document(
        str(doc_path),
        append_sections=[{"heading": "Phase 7 Status", "content": "Productivity Intelligence successfully verified."}],
        replace_pairs=[("1. Reliability", "1. Uncompromising Reliability")]
    )
    assert res_mod["modified"] is True

    # 4. Reopen modified and check content
    updated_data = DocumentManager.read_document(str(doc_path))
    assert "Phase 7 Status" in updated_data["headings"]
    assert "1. Uncompromising Reliability" in updated_data["text"]

    # 5. Validate Output
    assert DocumentManager.validate_document(str(doc_path), expected_title=title, expected_snippet="Phase 7 Status") is True


# ============================================================================
# 3. POWERPOINT / PRESENTATION TESTS (Create, Modify, Organize, Validate)
# ============================================================================

def test_presentation_lifecycle(tmp_path):
    """Verify presentation creation, slide additions, reorganization, and validation."""
    pres_path = tmp_path / "Product_Pitch.json"

    slides = [
        {
            "slide_number": 1,
            "title": "SPR SAATHI: Autonomous Computer Agent",
            "bullets": ["Pair programming assistant", "Local Win32 automation", "Phase-driven architecture"],
            "speaker_notes": "Welcome everyone to the demonstration."
        },
        {
            "slide_number": 2,
            "title": "Unified Perception Engine",
            "bullets": ["Multimodal vision", "Window hierarchy", "Running processes"],
            "speaker_notes": "Explain Phase 3 perception layer."
        }
    ]

    # 1. Create
    res_create = PresentationManager.create_presentation(str(pres_path), "Investor Deck", slides)
    assert os.path.exists(pres_path)
    assert res_create["slide_count"] == 2

    # 2. Reopen & Read
    deck = PresentationManager.read_presentation(str(pres_path))
    assert deck["presentation_title"] == "Investor Deck"
    assert len(deck["slides"]) == 2

    # 3. Modify (Add slide)
    new_slide = [{
        "slide_number": 3,
        "title": "Roadmap and Growth",
        "bullets": ["Phase 8 Memory", "Phase 9 Tools", "Phase 10 Multimodal Voice"],
        "speaker_notes": "Future development plan."
    }]
    res_mod = PresentationManager.modify_presentation(str(pres_path), add_slides=new_slide)
    assert res_mod["modified"] is True
    assert res_mod["new_slide_count"] == 3

    # 4. Validate Output
    assert PresentationManager.validate_presentation(str(pres_path), min_slides=3, expected_title="Investor Deck") is True
