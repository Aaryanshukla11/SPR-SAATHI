import pytest
import os
import asyncio

from agent.core.productivity import SpreadsheetManager, DocumentManager, PresentationManager
from agent.core.workspace import WorkspaceManager, FileOrigin, FileType
from agent.core.verification import MultiLevelVerifier, VerificationLevel
from agent.core.recovery import RecoveryStrategyEngine, FailureClassifier, FailureType, RecoveryAction
from agent.control.takeover import TakeoverManager, ControlState


# ============================================================================
# 1. FULL WORKFLOW: DATA -> EXCEL REPORT -> VERIFY -> DELIVER
# ============================================================================

@pytest.mark.asyncio
async def test_end_to_end_data_to_excel_report_and_deliverable(tmp_path):
    """
    Simulates the canonical Phase 18 task:
    'Take this data, create an Excel report, add calculations and save the final file.'
    Executes steps 1 through 9:
    1. Understand goal & setup workspace
    2. Access raw data
    3. Create spreadsheet with formulas
    4. Add calculations & summary metrics
    5. Generate structured report document
    6. Verify outputs with MultiLevelVerifier
    7. Register in WorkspaceManager as final deliverable
    """
    ws = WorkspaceManager(workspace_root=str(tmp_path))
    verifier = MultiLevelVerifier()

    # Step 1 & 2: Raw data
    headers = ["Department", "Budget", "Actual", "Variance"]
    rows = [
        ["R&D", "800000", "750000", "=B2-C2"],
        ["Product", "450000", "430000", "=B3-C3"],
        ["Sales", "600000", "590000", "=B4-C4"]
    ]
    formulas = {
        "Department": "TOTAL",
        "Budget": "=SUM(B2:B4)",
        "Actual": "=SUM(C2:C4)",
        "Variance": "=SUM(D2:D4)"
    }

    # Step 3 & 4: Create spreadsheet with formulas & calculations
    sheet_path = tmp_path / "FY26_Budget_Variance.csv"
    res_sheet = SpreadsheetManager.create_spreadsheet(str(sheet_path), headers, rows, formulas)
    assert res_sheet["row_count"] == 4

    # Analyze data
    analysis = SpreadsheetManager.analyze_spreadsheet(str(sheet_path))
    assert analysis["columns"]["Budget"]["sum"] == 1850000.0

    # Step 5: Generate report document
    doc_path = tmp_path / "FY26_Budget_Executive_Summary.md"
    res_doc = DocumentManager.create_document(
        str(doc_path),
        title="FY26 Budget Variance Executive Briefing",
        sections=[
            {"heading": "Key Finding", "content": f"Total Budget allocated was $1,850,000 across 3 departments."},
            {"heading": "Spreadsheet Location", "content": f"Detailed figures recorded in {os.path.basename(sheet_path)}."}
        ]
    )
    assert res_doc["sections_count"] == 2

    # Step 6: Multi-level verification
    file_verif = verifier.verify_file(str(sheet_path), expected_content="TOTAL")
    assert file_verif.passed is True

    doc_verif = verifier.verify_file(str(doc_path), expected_content="1,850,000")
    assert doc_verif.passed is True

    # Step 7: Deliver the result (Workspace deliverable tracking)
    meta_sheet = ws.register_file(str(sheet_path), origin=FileOrigin.FINAL_DELIVERABLE, task_id="task_e2e_1")
    meta_doc = ws.register_file(str(doc_path), origin=FileOrigin.FINAL_DELIVERABLE, task_id="task_e2e_1")

    deliverables = ws.get_files_by_origin(FileOrigin.FINAL_DELIVERABLE, task_id="task_e2e_1")
    assert len(deliverables) == 2
    assert any(d.filename == "FY26_Budget_Variance.csv" for d in deliverables)
    assert any(d.filename == "FY26_Budget_Executive_Summary.md" for d in deliverables)


# ============================================================================
# 2. CROSS-CAPABILITY TASKS (Data -> Document -> Presentation)
# ============================================================================

def test_cross_capability_task_orchestration(tmp_path):
    """Verify cross-capability orchestration combining Spreadsheets, Documents, and Presentations."""
    # 1. Document
    doc_file = tmp_path / "Architecture_Notes.md"
    DocumentManager.create_document(
        str(doc_file),
        title="SPR SAATHI Unified Framework",
        sections=[{"heading": "Overview", "content": "Autonomous desktop agent across 20 phases."}]
    )

    # 2. Presentation Deck
    pres_file = tmp_path / "Architecture_Deck.json"
    PresentationManager.create_presentation(
        str(pres_file),
        title="SPR SAATHI Overview",
        slides=[
            {"slide_number": 1, "title": "System Architecture", "bullets": ["Perception", "Recovery", "Skills"]}
        ]
    )

    # Verify both exist and are valid
    assert DocumentManager.validate_document(str(doc_file), expected_title="SPR SAATHI Unified Framework") is True
    assert PresentationManager.validate_presentation(str(pres_file), min_slides=1, expected_title="SPR SAATHI") is True


# ============================================================================
# 3. USER INTERRUPTIONS & RECOVERY ESCALATION
# ============================================================================

def test_workflow_user_interruption_and_resume():
    """Verify human takeover interruption safely transitions control state."""
    takeover = TakeoverManager()
    assert takeover.control_state == ControlState.AI_CONTROL

    # User initiates takeover
    took = takeover.take_control()
    assert took is True
    assert takeover.control_state == ControlState.HUMAN_CONTROL
    assert takeover.is_takeover_active is True

    # User releases control
    released = takeover.release_control()
    assert released is True
    assert takeover.control_state == ControlState.AI_CONTROL
    assert takeover.is_takeover_active is False


def test_workflow_failure_recovery_escalation():
    """Verify failure recovery pipeline classifies missing file and determines recovery strategy."""
    recovery_engine = RecoveryStrategyEngine()
    recovery_engine.reset_for_new_task()

    tool_res = {"success": False, "error": "FileNotFoundError: File 'data.csv' was not found"}
    fail_class = FailureClassifier.classify("read_file", tool_res)

    assert fail_class.failure_type == FailureType.FILE_FAILURE

    action, reason, alt = recovery_engine.determine_recovery_strategy("read_file", fail_class)
    # Graduated recovery: first attempt is retry safely or alternative
    assert action in (RecoveryAction.RETRY_SAFELY, RecoveryAction.REPLAN)
