import pytest
import os
import time

from agent.core.workspace import (
    WorkspaceManager, FileType, FileOrigin, FileMetadata, WORKSPACE_MANAGER
)


# ============================================================================
# 1. FILE TYPE UNDERSTANDING & METADATA TESTS
# ============================================================================

def test_file_type_categorization():
    """Verify detect_file_type accurately categorizes files by format."""
    mgr = WorkspaceManager()

    assert mgr.detect_file_type("report.pdf") == FileType.DOCUMENT
    assert mgr.detect_file_type("notes.docx") == FileType.DOCUMENT
    assert mgr.detect_file_type("financials.xlsx") == FileType.SPREADSHEET
    assert mgr.detect_file_type("data.csv") == FileType.SPREADSHEET
    assert mgr.detect_file_type("pitch.pptx") == FileType.PRESENTATION
    assert mgr.detect_file_type("diagram.png") == FileType.IMAGE
    assert mgr.detect_file_type("main.py") == FileType.CODE
    assert mgr.detect_file_type("archive.zip") == FileType.ARCHIVE
    assert mgr.detect_file_type("readme.md") == FileType.TEXT


def test_file_registration_and_metadata_extraction(tmp_path):
    """Verify register_file extracts size, hash, and timestamps."""
    mgr = WorkspaceManager(workspace_root=str(tmp_path))
    sample = tmp_path / "sample.py"
    sample.write_text("print('SPR SAATHI')")

    meta = mgr.register_file(str(sample), origin=FileOrigin.AGENT_GENERATED, task_id="task_123")
    assert meta is not None
    assert meta.filename == "sample.py"
    assert meta.file_type == FileType.CODE
    assert meta.file_origin == FileOrigin.AGENT_GENERATED
    assert meta.parent_task_id == "task_123"
    assert len(meta.sha256_hash) == 64
    assert meta.size_bytes > 0


# ============================================================================
# 2. FILE MODIFICATION & CHECKSUM TRACKING TESTS
# ============================================================================

def test_track_file_modification(tmp_path):
    """Verify track_file_modification detects hash change and logs history."""
    mgr = WorkspaceManager(workspace_root=str(tmp_path))
    doc = tmp_path / "budget.xlsx"
    doc.write_text("Initial budget: $10,000")

    mgr.register_file(str(doc), origin=FileOrigin.EXISTING)
    orig_hash = mgr.tracked_files[str(doc)].sha256_hash

    # No change yet
    changed = mgr.track_file_modification(str(doc))
    assert changed is False

    # Modify file
    time.sleep(0.01)
    doc.write_text("Updated budget: $15,000")
    changed = mgr.track_file_modification(str(doc), modifier="agent")
    assert changed is True

    new_hash = mgr.tracked_files[str(doc)].sha256_hash
    assert new_hash != orig_hash
    assert len(mgr.modification_history) == 1
    assert mgr.modification_history[0]["old_hash"] == orig_hash
    assert mgr.modification_history[0]["new_hash"] == new_hash


# ============================================================================
# 3. INTELLIGENT FILE SEARCH & RANKING TESTS
# ============================================================================

def test_intelligent_file_search_and_ranking(tmp_path):
    """Verify search_files scores exact matches higher than partial matches and filters by type."""
    mgr = WorkspaceManager(workspace_root=str(tmp_path))

    # Create dummy files
    (tmp_path / "presentation_final.pptx").write_text("dummy pptx")
    (tmp_path / "presentation_draft.pptx").write_text("dummy draft")
    (tmp_path / "notes_about_presentation.txt").write_text("dummy notes")
    (tmp_path / "unrelated_code.py").write_text("dummy code")

    # Search for "presentation_final"
    results = mgr.search_files("presentation_final", search_dirs=[str(tmp_path)])
    assert len(results) > 0
    top_file, top_score = results[0]
    assert top_file.filename == "presentation_final.pptx"

    # Filter by PRESENTATION file type
    pres_results = mgr.search_files("presentation", file_types=[FileType.PRESENTATION], search_dirs=[str(tmp_path)])
    assert len(pres_results) == 2
    for meta, _ in pres_results:
        assert meta.file_type == FileType.PRESENTATION


# ============================================================================
# 4. LIFECYCLE ORIGIN & DELIVERABLE TRACKING TESTS
# ============================================================================

def test_lifecycle_origin_filtering(tmp_path):
    """Verify get_files_by_origin separates user uploads, artifacts, and final deliverables."""
    mgr = WorkspaceManager(workspace_root=str(tmp_path))

    upload = tmp_path / "input_data.csv"
    upload.write_text("col1,col2")
    mgr.register_file(str(upload), origin=FileOrigin.USER_UPLOAD, task_id="task_A")

    deliverable = tmp_path / "final_report.pdf"
    deliverable.write_text("report content")
    mgr.register_file(str(deliverable), origin=FileOrigin.FINAL_DELIVERABLE, task_id="task_A")

    artifact = tmp_path / "temp_chart.png"
    artifact.write_text("chart data")
    mgr.register_file(str(artifact), origin=FileOrigin.INTERMEDIATE_ARTIFACT, task_id="task_A")

    uploads = mgr.get_files_by_origin(FileOrigin.USER_UPLOAD, task_id="task_A")
    assert len(uploads) == 1
    assert uploads[0].filename == "input_data.csv"

    deliverables = mgr.get_files_by_origin(FileOrigin.FINAL_DELIVERABLE, task_id="task_A")
    assert len(deliverables) == 1
    assert deliverables[0].filename == "final_report.pdf"

    artifacts = mgr.get_files_by_origin(FileOrigin.INTERMEDIATE_ARTIFACT, task_id="task_A")
    assert len(artifacts) == 1
    assert artifacts[0].filename == "temp_chart.png"
