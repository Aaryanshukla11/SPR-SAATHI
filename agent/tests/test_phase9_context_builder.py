import pytest
from unittest.mock import patch, MagicMock

from agent.core.context import (
    ContextBuilder, CONTEXT_BUILDER, sanitize_sensitive_data, build_compact_context
)
from agent.core.memory import MemoryItem, MemoryType
from agent.core.workspace import FileMetadata, FileType, FileOrigin


# ============================================================================
# 1. PRIVACY BOUNDARIES & SANITIZATION TESTS
# ============================================================================

def test_privacy_boundary_redacts_api_keys_and_passwords():
    """Verify sanitize_sensitive_data redacts OpenAI/Google/GitHub keys, tokens, and passwords."""
    raw_prompt = (
        "Configure OpenAI key sk-abcdef1234567890abcdef1234567890\n"
        "Google API key AIzaSyD12345678901234567890123456789012\n"
        "GitHub token ghp_123456789012345678901234567890123456\n"
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghij\n"
        "password: mySuperSecretPassword123!\n"
    )

    clean = sanitize_sensitive_data(raw_prompt)

    assert "sk-abcdef" not in clean
    assert "[REDACTED_API_KEY]" in clean

    assert "AIzaSyD" not in clean
    assert "[REDACTED_GOOGLE_KEY]" in clean

    assert "ghp_123" not in clean
    assert "[REDACTED_GITHUB_TOKEN]" in clean

    assert "eyJhbGci" not in clean
    assert "[REDACTED_TOKEN]" in clean

    assert "mySuperSecretPassword123!" not in clean
    assert "[REDACTED]" in clean


# ============================================================================
# 2. LARGE HISTORY SLIDING WINDOW & BOUNDS TESTS
# ============================================================================

def test_large_history_sliding_window():
    """Verify context builder limits action history to sliding window to prevent token explosion."""
    builder = ContextBuilder()

    # Generate 50 simulated historical actions
    large_history = []
    for i in range(50):
        large_history.append({
            "action": f"tool_step_{i}",
            "parameters": {"param": i},
            "status": "completed",
            "output": f"Result {i}"
        })

    sys_prompt, user_content = builder.build_context(
        goal="Complete task",
        plan=[{"description": "Step 1", "status": "pending"}],
        observation={},
        recent_history=large_history,
        include_memories=False,
        include_workspace_files=False
    )

    # History slice should be bounded to max_items (e.g. 6 items), not all 50
    assert "tool_step_49" in user_content
    assert "tool_step_0" not in user_content, "Oldest history steps must be pruned by sliding window"


# ============================================================================
# 3. RELEVANT MEMORY RETRIEVAL & ACCURACY TESTS
# ============================================================================

def test_relevant_memories_injection():
    """Verify relevant memories matching goal are accurately retrieved and injected."""
    builder = ContextBuilder()

    fake_memory = MemoryItem(
        id="mem_1",
        memory_type=MemoryType.PREFERENCE_MEMORY,
        key="preferred_editor",
        content="VS Code"
    )

    with patch("agent.core.memory.MEMORY_MANAGER.retrieve_relevant", return_value=[(fake_memory, 5.0)]):
        sys_prompt, user_content = builder.build_context(
            goal="Open my preferred editor",
            plan=[],
            observation={},
            recent_history=[],
            include_memories=True,
            include_workspace_files=False
        )

        assert "=== RELEVANT USER MEMORIES ===" in user_content
        assert "[preferred_editor]: VS Code" in user_content


# ============================================================================
# 4. RELEVANT WORKSPACE FILES RETRIEVAL TESTS
# ============================================================================

def test_relevant_workspace_files_injection():
    """Verify relevant workspace files matching goal are included in prompt context."""
    builder = ContextBuilder()

    fake_file = FileMetadata(
        path="C:\\Projects\\quarterly_report.xlsx",
        filename="quarterly_report.xlsx",
        extension=".xlsx",
        size_bytes=24500,
        created_time=1000.0,
        modified_time=2000.0,
        file_type=FileType.SPREADSHEET,
        file_origin=FileOrigin.FINAL_DELIVERABLE,
        sha256_hash="dummy_hash"
    )

    with patch("agent.core.workspace.WORKSPACE_MANAGER.search_files", return_value=[(fake_file, 10.0)]):
        sys_prompt, user_content = builder.build_context(
            goal="Update the quarterly report spreadsheet",
            plan=[],
            observation={},
            recent_history=[],
            include_memories=False,
            include_workspace_files=True
        )

        assert "=== RELEVANT WORKSPACE FILES ===" in user_content
        assert "quarterly_report.xlsx" in user_content
        assert "spreadsheet" in user_content


# ============================================================================
# 5. CONVERSATION HISTORY INTEGRATION
# ============================================================================

def test_conversation_history_integration():
    """Verify previous conversational turns are formatted in context."""
    builder = ContextBuilder()

    conv_turns = [
        {"role": "user", "message": "Can you summarize the document?"},
        {"role": "assistant", "message": "I will inspect and summarize the document now."}
    ]

    sys_prompt, user_content = builder.build_context(
        goal="Summarize document",
        plan=[],
        observation={},
        recent_history=[],
        conversation_history=conv_turns,
        include_memories=False,
        include_workspace_files=False
    )

    assert "=== RECENT CONVERSATION ===" in user_content
    assert "User: Can you summarize the document?" in user_content
    assert "Assistant: I will inspect and summarize the document now." in user_content
