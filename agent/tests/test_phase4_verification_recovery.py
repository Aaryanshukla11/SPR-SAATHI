import pytest
from unittest.mock import patch, MagicMock

from agent.core.verification import (
    MultiLevelVerifier, VerificationLevel, VerificationResult, VERIFIER
)
from agent.core.recovery import (
    FailureClassifier, FailureType, FailureClassification,
    RecoveryAction, RecoveryStrategyEngine, RECOVERY_ENGINE
)


# ============================================================================
# 1. MULTI-LEVEL VERIFICATION TESTS
# ============================================================================

def test_tool_verification_success_and_failure():
    """Verify Level 1 Tool verification identifies success and failure results."""
    verifier = MultiLevelVerifier()

    res_ok = verifier.verify_tool({"success": True, "output": "Done", "error": None})
    assert res_ok.passed is True
    assert res_ok.level == VerificationLevel.TOOL

    res_err = verifier.verify_tool({"success": False, "output": "", "error": "Command failed"})
    assert res_err.passed is False
    assert "Command failed" in res_err.details


def test_application_verification_responsive_and_hung():
    """Verify Level 2 Application verification flags unresponsive windows."""
    verifier = MultiLevelVerifier()

    with patch("agent.core.win32_utils.IS_WINDOWS", True), \
         patch("agent.core.win32_utils.is_window_responsive", return_value=True):
        res = verifier.verify_application("notepad.exe", expected_hwnd=123)
        assert res.passed is True
        assert res.level == VerificationLevel.APPLICATION

    with patch("agent.core.win32_utils.IS_WINDOWS", True), \
         patch("agent.core.win32_utils.is_window_responsive", return_value=False):
        res = verifier.verify_application("notepad.exe", expected_hwnd=123)
        assert res.passed is False
        assert "hung" in res.details


def test_file_verification_existence_and_content(tmp_path):
    """Verify Level 3 File verification checks file existence, size, and snippet presence."""
    verifier = MultiLevelVerifier()
    test_file = tmp_path / "report.txt"

    # Missing file
    res_missing = verifier.verify_file(str(test_file), must_exist=True)
    assert res_missing.passed is False
    assert "does not exist" in res_missing.details

    # Create file
    test_file.write_text("Revenue: $500,000\nProfit: $120,000")

    # Existing file with expected snippet
    res_valid = verifier.verify_file(str(test_file), expected_content="Revenue: $500,000")
    assert res_valid.passed is True
    assert res_valid.metrics["size_bytes"] > 0

    # Existing file with missing snippet
    res_bad_snippet = verifier.verify_file(str(test_file), expected_content="NonExistentCompany")
    assert res_bad_snippet.passed is False
    assert "does not contain expected snippet" in res_bad_snippet.details


def test_data_verification_schema_and_regex():
    """Verify Level 4 Data verification verifies dictionary keys and regex expressions."""
    verifier = MultiLevelVerifier()

    data = {"status": "ok", "token": "abc-12345", "count": 42}
    res_ok = verifier.verify_data(data, expected_keys=["status", "token"])
    assert res_ok.passed is True

    res_missing = verifier.verify_data(data, expected_keys=["status", "missing_field"])
    assert res_missing.passed is False
    assert "missing_field" in res_missing.details

    res_regex_ok = verifier.verify_data("Order #98765 confirmed", expected_pattern=r"Order #\d+")
    assert res_regex_ok.passed is True

    res_regex_fail = verifier.verify_data("Error 500", expected_pattern=r"Order #\d+")
    assert res_regex_fail.passed is False


def test_visual_verification_detects_pixels():
    """Verify Level 5 Visual verification flags absence of visual change."""
    verifier = MultiLevelVerifier()

    obs_no_change = {"image_path": "fake_path_1.jpg"}
    obs_after = {"image_path": "fake_path_2.jpg"}

    fake_diff_no_change = {"change_detected": False, "pixels_changed": 0}
    with patch("PIL.Image.open"), \
         patch("agent.core.verification.verify_visual_change", return_value=fake_diff_no_change):
        res = verifier.verify_visual(obs_no_change, obs_after, expect_change=True)
        assert res.passed is False
        assert "screen pixels did not change" in res.details

    fake_diff_changed = {"change_detected": True, "pixels_changed": 150}
    with patch("PIL.Image.open"), \
         patch("agent.core.verification.verify_visual_change", return_value=fake_diff_changed):
        res = verifier.verify_visual(obs_no_change, obs_after, expect_change=True)
        assert res.passed is True


# ============================================================================
# 2. FAILURE CLASSIFICATION TESTS
# ============================================================================

def test_failure_classification_taxonomy():
    """Verify FailureClassifier correctly tags failures into Phase 4 taxonomy."""
    # 1. Permission failure
    tool_perm_err = {"success": False, "error": "Permission denied by security policy"}
    cf = FailureClassifier.classify("delete_file", tool_perm_err, {})
    assert cf is not None
    assert cf.failure_type == FailureType.PERMISSION_FAILURE

    # 2. File verification failure
    vf_file_fail = {
        VerificationLevel.TOOL: VerificationResult(VerificationLevel.TOOL, True, "OK"),
        VerificationLevel.FILE: VerificationResult(VerificationLevel.FILE, False, "File missing")
    }
    cf = FailureClassifier.classify("create_file", {"success": True}, vf_file_fail)
    assert cf is not None
    assert cf.failure_type == FailureType.FILE_FAILURE

    # 3. Application verification failure
    vf_app_fail = {
        VerificationLevel.TOOL: VerificationResult(VerificationLevel.TOOL, True, "OK"),
        VerificationLevel.APPLICATION: VerificationResult(VerificationLevel.APPLICATION, False, "App hung")
    }
    cf = FailureClassifier.classify("launch_app", {"success": True}, vf_app_fail)
    assert cf is not None
    assert cf.failure_type == FailureType.APPLICATION_FAILURE

    # 4. Visual verification failure
    vf_vis_fail = {
        VerificationLevel.TOOL: VerificationResult(VerificationLevel.TOOL, True, "OK"),
        VerificationLevel.VISUAL: VerificationResult(VerificationLevel.VISUAL, False, "No change")
    }
    cf = FailureClassifier.classify("mouse_click", {"success": True}, vf_vis_fail)
    assert cf is not None
    assert cf.failure_type == FailureType.VERIFICATION_FAILURE


# ============================================================================
# 3. GRADUATED RECOVERY STRATEGY TESTS
# ============================================================================

def test_graduated_recovery_pipeline():
    """Verify graduated recovery: Retry -> Alternative Tool -> Replan -> Ask User -> Stop."""
    engine = RecoveryStrategyEngine(max_action_retries=2, max_replans=1, max_total_failures=5)
    action = "cmd"
    fail = FailureClassification(FailureType.TOOL_FAILURE, "Syntax error")

    # Attempt 1: RETRY_SAFELY
    strategy, reason, alt = engine.determine_recovery_strategy(action, fail)
    assert strategy == RecoveryAction.RETRY_SAFELY
    assert "Attempt 1/2" in reason

    # Attempt 2: RETRY_SAFELY
    strategy, reason, alt = engine.determine_recovery_strategy(action, fail)
    assert strategy == RecoveryAction.RETRY_SAFELY
    assert "Attempt 2/2" in reason

    # Attempt 3: ALTERNATIVE_TOOL (cmd -> powershell)
    strategy, reason, alt = engine.determine_recovery_strategy(action, fail)
    assert strategy == RecoveryAction.ALTERNATIVE_TOOL
    assert alt == "powershell"

    # Simulate powershell also failing
    ps_fail = FailureClassification(FailureType.TOOL_FAILURE, "Powershell error")
    engine.action_retry_counts["powershell"] = 2  # pretend retries exhausted for alternative

    # Attempt 4: REPLAN
    strategy, reason, alt = engine.determine_recovery_strategy("powershell", ps_fail)
    assert strategy == RecoveryAction.REPLAN

    # Attempt 5: Exceeded replan -> ASK_USER
    strategy, reason, alt = engine.determine_recovery_strategy("powershell", ps_fail)
    assert strategy == RecoveryAction.ASK_USER

    # Attempt 6: Exceeded total failure limit -> STOP
    strategy, reason, alt = engine.determine_recovery_strategy("powershell", ps_fail)
    assert strategy == RecoveryAction.STOP
    assert "Exceeded total failure limit" in reason


def test_permission_failure_immediately_asks_user():
    """Verify permission failure jumps directly to Ask User without wasting retries."""
    engine = RecoveryStrategyEngine()
    perm_fail = FailureClassification(FailureType.PERMISSION_FAILURE, "Access denied")

    strategy, reason, alt = engine.determine_recovery_strategy("delete_system_file", perm_fail)
    assert strategy == RecoveryAction.ASK_USER
    assert "requires elevated permission" in reason
