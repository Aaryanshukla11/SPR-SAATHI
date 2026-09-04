import pytest
import os
import csv
import json

from agent.skills import get_skill_registry, SKILL_REGISTRY
from agent.skills.base import BaseSkill, SkillExecutionResult
from agent.skills.file_organizer import OrganizeFilesSkill
from agent.skills.document_creator import CreateDocumentSkill
from agent.skills.data_analysis import AnalyzeDatasetSkill
from agent.skills.research import ResearchTopicSkill


# ============================================================================
# 1. SKILL DEFINITION & DISCOVERY TESTS
# ============================================================================

def test_skills_satisfy_eight_required_attributes():
    """Verify every registered skill defines all 8 required Phase 5 attributes."""
    reg = get_skill_registry()
    skills = reg.list_skills()
    assert len(skills) >= 4

    for s in skills:
        assert s["name"], "Skill must have name"
        assert s["description"], "Skill must have description"
        assert isinstance(s["input_schema"], dict), "Skill must have input_schema"
        assert isinstance(s["output_schema"], dict), "Skill must have output_schema"
        assert isinstance(s["required_permissions"], list), "Skill must have required_permissions"
        assert isinstance(s["required_tools"], list), "Skill must have required_tools"
        assert s["verification_strategy"], "Skill must have verification_strategy"
        assert s["fallback_strategy"], "Skill must have fallback_strategy"


def test_skill_discovery_and_relevance_ranking():
    """Verify skill discovery accurately ranks skills matching user goals."""
    reg = get_skill_registry()

    # Goal 1: Organize files
    matches = reg.discover_skills_for_goal("Please organize all my files on the desktop")
    assert len(matches) > 0
    top_skill, score = matches[0]
    assert top_skill.name == "organize_files"

    # Goal 2: Document creation
    matches = reg.discover_skills_for_goal("Create a report document for quarterly earnings")
    assert len(matches) > 0
    top_skill, score = matches[0]
    assert top_skill.name == "create_document"

    # Goal 3: Dataset analysis
    matches = reg.discover_skills_for_goal("Analyze dataset CSV file")
    assert len(matches) > 0
    top_skill, score = matches[0]
    assert top_skill.name == "analyze_dataset"


# ============================================================================
# 2. FILE ORGANIZER SKILL EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_organize_files_skill_execution(tmp_path):
    """Verify OrganizeFilesSkill categorizes files into subdirectories and verifies movement."""
    # Create sample files
    (tmp_path / "invoice.pdf").write_text("dummy invoice")
    (tmp_path / "photo.png").write_text("dummy photo")
    (tmp_path / "script.py").write_text("print('hello')")
    (tmp_path / "archive.zip").write_text("dummy zip")

    skill = OrganizeFilesSkill()
    res = await skill.execute({"directory_path": str(tmp_path)})

    assert res.success is True
    assert res.output["files_moved"] == 4
    assert "Documents" in res.output["categories_created"]
    assert "Images" in res.output["categories_created"]
    assert "Code" in res.output["categories_created"]
    assert "Archives" in res.output["categories_created"]

    # Verify physical files moved
    assert os.path.exists(tmp_path / "Documents" / "invoice.pdf")
    assert os.path.exists(tmp_path / "Images" / "photo.png")
    assert os.path.exists(tmp_path / "Code" / "script.py")
    assert os.path.exists(tmp_path / "Archives" / "archive.zip")
    assert res.verification_details["verified"] is True


@pytest.mark.asyncio
async def test_organize_files_non_existent_directory():
    """Verify OrganizeFilesSkill cleanly fails on non-existent directory."""
    skill = OrganizeFilesSkill()
    res = await skill.execute({"directory_path": "C:\\non_existent_dir_xyz_12345"})
    assert res.success is False
    assert "does not exist" in res.error


# ============================================================================
# 3. DOCUMENT CREATOR SKILL EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_document_skill_execution(tmp_path):
    """Verify CreateDocumentSkill writes structured markdown report and verifies content."""
    doc_path = tmp_path / "Quarterly_Report.md"
    skill = CreateDocumentSkill()

    inputs = {
        "file_path": str(doc_path),
        "title": "Q3 Performance Briefing",
        "sections": [
            {"heading": "Executive Summary", "content": "Operations exceeded revenue projections."},
            {"heading": "Key Milestones", "content": "Delivered Phase 5 Skills Framework."}
        ],
        "author": "Antigravity AI"
    }

    res = await skill.execute(inputs)
    assert res.success is True
    assert res.output["sections_written"] == 2
    assert os.path.exists(doc_path)
    assert res.verification_details["title_verified"] is True

    content = doc_path.read_text(encoding="utf-8")
    assert "# Q3 Performance Briefing" in content
    assert "## Executive Summary" in content
    assert "## Key Milestones" in content


# ============================================================================
# 4. DATASET ANALYSIS SKILL EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_analyze_dataset_skill_csv(tmp_path):
    """Verify AnalyzeDatasetSkill calculates row counts and column statistics on CSV files."""
    csv_file = tmp_path / "sales.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["item", "units", "price"])
        writer.writerow(["Piston Ring Set", "100", "45.50"])
        writer.writerow(["Cylinder Liner", "50", "120.00"])
        writer.writerow(["Gasket Kit", "200", "15.25"])

    skill = AnalyzeDatasetSkill()
    res = await skill.execute({"file_path": str(csv_file)})

    assert res.success is True
    assert res.output["row_count"] == 3
    assert res.output["column_count"] == 3
    assert "units" in res.output["summary"]
    assert res.output["summary"]["units"]["min"] == 50.0
    assert res.output["summary"]["units"]["max"] == 200.0


@pytest.mark.asyncio
async def test_analyze_dataset_skill_json(tmp_path):
    """Verify AnalyzeDatasetSkill analyzes JSON records."""
    json_file = tmp_path / "records.json"
    data = [
        {"sensor": "temp_1", "reading": 72.5},
        {"sensor": "temp_2", "reading": 80.0},
        {"sensor": "temp_3", "reading": 68.0}
    ]
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    skill = AnalyzeDatasetSkill()
    res = await skill.execute({"file_path": str(json_file)})

    assert res.success is True
    assert res.output["row_count"] == 3
    assert res.output["summary"]["reading"]["mean"] == 73.5


# ============================================================================
# 5. RESEARCH TOPIC SKILL EXECUTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_research_topic_skill_execution():
    """Verify ResearchTopicSkill produces structured findings and briefing."""
    skill = ResearchTopicSkill()
    res = await skill.execute({
        "topic": "High-DPI Coordinate Scaling on Windows 11",
        "sources": ["https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows"]
    })

    assert res.success is True
    assert res.output["topic"] == "High-DPI Coordinate Scaling on Windows 11"
    assert len(res.output["key_findings"]) >= 3
    assert "Research Briefing" in res.output["briefing"]
