import pytest

from agent.core.specialists import (
    SpecialistDelegator, SpecialistType, KairoCodingSpecialist,
    ResearchSpecialist, DataAnalysisSpecialist, SPECIALIST_DELEGATOR
)


# ============================================================================
# 1. SPECIALIST DETECTION TESTS
# ============================================================================

def test_detect_kairo_ai_coding_specialist():
    """Verify coding requests route to KAIRO-AI coding specialist."""
    delegator = SpecialistDelegator()
    spec = delegator.detect_specialist("Write a python script to compute fibonacci numbers")
    assert spec is not None
    assert spec.specialist_type == SpecialistType.CODING
    assert "KAIRO-AI" in spec.name


def test_detect_research_specialist():
    """Verify research requests route to research specialist."""
    delegator = SpecialistDelegator()
    spec = delegator.detect_specialist("Research recent advancements in transformer architectures")
    assert spec is not None
    assert spec.specialist_type == SpecialistType.RESEARCH


def test_detect_data_analysis_specialist():
    """Verify dataset requests route to data analysis specialist."""
    delegator = SpecialistDelegator()
    spec = delegator.detect_specialist("Analyze dataset metrics and statistics from sales CSV")
    assert spec is not None
    assert spec.specialist_type == SpecialistType.DATA_ANALYSIS


# ============================================================================
# 2. KAIRO-AI CODING WORKFLOW & AST VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_kairo_ai_coding_workflow_and_verification():
    """Verify KAIRO-AI generates code, verifies AST syntax, and returns artifacts."""
    specialist = KairoCodingSpecialist()
    res = await specialist.execute("Write a python function to compute fibonacci numbers")

    assert res.success is True
    assert res.verification_passed is True
    assert "solution.py" in res.code_artifacts
    assert "def fibonacci" in res.code_artifacts["solution.py"]


@pytest.mark.asyncio
async def test_kairo_ai_detects_syntax_errors():
    """Verify KAIRO-AI detects malformed code syntax."""
    specialist = KairoCodingSpecialist()
    bad_code = "def broken_syntax(:\n    return 123"
    res = await specialist.execute("Verify this script", context={"code": bad_code})

    assert res.success is False
    assert res.verification_passed is False
    assert "Syntax error" in res.error


# ============================================================================
# 3. DELEGATION & FALLBACK HANDLING
# ============================================================================

@pytest.mark.asyncio
async def test_delegator_end_to_end():
    """Verify SpecialistDelegator end-to-end delegation and handoff."""
    delegator = SpecialistDelegator()
    result = await delegator.delegate_task("Implement a python script for sorting")

    assert result is not None
    assert result.success is True
    assert result.specialist_type == SpecialistType.CODING
