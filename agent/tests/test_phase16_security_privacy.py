import pytest
import os
import json
import asyncio
from unittest.mock import AsyncMock

from agent.permissions.policies import PolicyManager, DEFAULT_POLICIES
from agent.permissions.broker import PermissionBroker
from agent.core.state import StateTracker


# ============================================================================
# 1. ALLOW & DENY POLICIES TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_allow_policy_immediate_execution(tmp_path):
    """Verify 'allow' policy immediately approves tool call and logs to audit trail."""
    cfg = tmp_path / "permissions.json"
    pm = PolicyManager(config_path=str(cfg))
    pm.update_policy("filesystem", "allow")

    st = StateTracker()
    st.task_id = "test_task_allow"
    broker = PermissionBroker(pm, state_tracker=st)

    allowed = await broker.check_permission("read_file", "filesystem", {"path": "test.txt"})
    assert allowed is True
    assert len(broker.audit_trail) == 1
    assert broker.audit_trail[0]["decision"] == "allow"
    assert broker.audit_trail[0]["source"] == "system"


@pytest.mark.asyncio
async def test_deny_policy_immediate_block(tmp_path):
    """Verify 'deny' policy immediately blocks execution and logs to audit trail."""
    cfg = tmp_path / "permissions.json"
    pm = PolicyManager(config_path=str(cfg))
    pm.update_policy("terminal", "deny")

    st = StateTracker()
    st.task_id = "test_task_deny"
    broker = PermissionBroker(pm, state_tracker=st)

    allowed = await broker.check_permission("cmd", "terminal", {"command": "dir"})
    assert allowed is False
    assert len(broker.audit_trail) == 1
    assert broker.audit_trail[0]["decision"] == "deny"


# ============================================================================
# 2. PERMISSION PERSISTENCE TESTS
# ============================================================================

def test_permission_persistence(tmp_path):
    """Verify updating policy persists to JSON and reloads across instances."""
    cfg = tmp_path / "persisted_permissions.json"
    pm1 = PolicyManager(config_path=str(cfg))
    pm1.update_policy("terminal", "allow")
    pm1.update_app_policy("custom_app.exe", "allow")

    assert os.path.exists(cfg)

    # Instantiate new manager loading from same file
    pm2 = PolicyManager(config_path=str(cfg))
    assert pm2.policies["terminal"] == "allow"
    assert pm2.app_policies["custom_app.exe"] == "allow"


# ============================================================================
# 3. APPLICATION SPECIFIC OVERRIDES TESTS
# ============================================================================

def test_application_specific_overrides(tmp_path):
    """Verify specific app policy overrides generic application category rule."""
    cfg = tmp_path / "permissions.json"
    pm = PolicyManager(config_path=str(cfg))
    pm.update_policy("applications", "deny")  # Generic deny
    pm.update_app_policy("notepad.exe", "allow")  # Specific allow override

    # Check launch_app with notepad -> should be allow
    res_notepad = pm.get_policy("launch_app", "applications", {"app_name": "notepad.exe"})
    assert res_notepad == "allow"

    # Check launch_app with other app -> should be deny
    res_other = pm.get_policy("launch_app", "applications", {"app_name": "random_tool.exe"})
    assert res_other == "deny"


# ============================================================================
# 4. SENSITIVE OPERATIONS & PROMPT RESOLUTION
# ============================================================================

@pytest.mark.asyncio
async def test_prompt_policy_user_resolution(tmp_path):
    """Verify 'prompt' policy waits for user callback and resolves allowed decision."""
    cfg = tmp_path / "permissions.json"
    pm = PolicyManager(config_path=str(cfg))
    pm.update_policy("mouse", "prompt")

    st = StateTracker()
    broker = PermissionBroker(pm, state_tracker=st)

    async def mock_prompt(req_id, tool_name, args):
        # User approves after short delay
        asyncio.create_task(resolve_later(broker, req_id, "allow"))

    async def resolve_later(b, r_id, dec):
        await asyncio.sleep(0.05)
        b.resolve_permission(r_id, dec)

    broker.on_prompt_callback = mock_prompt

    allowed = await broker.check_permission("mouse_click", "computer", {"x": 100, "y": 100})
    assert allowed is True
    assert len(broker.audit_trail) == 1
    assert broker.audit_trail[0]["decision"] == "allow"
    assert broker.audit_trail[0]["source"] == "user"


# ============================================================================
# 5. AUDIT LOG INTEGRITY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_audit_log_records_chronological_trace(tmp_path):
    """Verify audit log records all operations with timestamps, task_id, and scopes."""
    cfg = tmp_path / "permissions.json"
    pm = PolicyManager(config_path=str(cfg))
    pm.update_policy("filesystem", "allow")
    pm.update_policy("terminal", "deny")

    st = StateTracker()
    st.task_id = "audit_task_99"
    broker = PermissionBroker(pm, state_tracker=st)

    await broker.check_permission("read_file", "filesystem", {"path": "a.txt"})
    await broker.check_permission("cmd", "terminal", {"command": "dir"})

    assert len(broker.audit_trail) == 2
    assert broker.audit_trail[0]["scope"] == "filesystem"
    assert broker.audit_trail[1]["scope"] == "terminal"
    assert broker.audit_trail[0]["task_id"] == "audit_task_99"
    assert broker.audit_trail[1]["task_id"] == "audit_task_99"
