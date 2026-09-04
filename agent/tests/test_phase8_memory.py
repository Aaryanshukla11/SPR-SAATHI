import pytest
import os

from agent.core.memory import (
    MemoryManager, MemoryType, MemoryItem, MEMORY_MANAGER
)


# ============================================================================
# 1. MEMORY CREATION ACROSS 5 TIERS
# ============================================================================

def test_memory_creation_across_tiers(tmp_path):
    """Verify memory creation across Conversation, Short-Term, Long-Term, Preference, and Project tiers."""
    store_file = tmp_path / "test_memory.json"
    mgr = MemoryManager(storage_path=str(store_file))

    # 1. Conversation turn
    mgr.record_conversation_turn("user", "Please open the report", session_id="s1")
    mgr.record_conversation_turn("assistant", "I am opening the report", session_id="s1")
    history = mgr.get_conversation_history(session_id="s1")
    assert len(history) == 2
    assert history[0]["role"] == "user"

    # 2. Preference Memory
    pref = mgr.add_memory(
        MemoryType.PREFERENCE_MEMORY,
        key="preferred_editor",
        content="VS Code",
        tags=["ide", "coding"]
    )
    assert pref.memory_type == MemoryType.PREFERENCE_MEMORY
    assert pref.content == "VS Code"

    # 3. Project Memory
    proj = mgr.add_memory(
        MemoryType.PROJECT_MEMORY,
        key="target_platform",
        content="Windows 11 x64 Win32 Native",
        tags=["architecture", "platform"]
    )
    assert proj.memory_type == MemoryType.PROJECT_MEMORY

    # 4. Long-Term Memory
    ltm = mgr.add_memory(
        MemoryType.LONG_TERM_MEMORY,
        key="user_name",
        content="Aaryan Shukla",
        tags=["identity"]
    )
    assert ltm.content == "Aaryan Shukla"

    # 5. Short-Term Context
    stm = mgr.add_memory(
        MemoryType.SHORT_TERM_CONTEXT,
        key="active_task_state",
        content="Generating quarterly brief",
        tags=["task_ctx"]
    )
    assert stm.key == "active_task_state"


# ============================================================================
# 2. RELEVANCE RETRIEVAL TESTS
# ============================================================================

def test_relevance_retrieval(tmp_path):
    """Verify retrieve_relevant accurately scores memories matching queries."""
    store_file = tmp_path / "test_memory.json"
    mgr = MemoryManager(storage_path=str(store_file))

    mgr.add_memory(MemoryType.PREFERENCE_MEMORY, key="browser", content="Google Chrome", tags=["web"])
    mgr.add_memory(MemoryType.PREFERENCE_MEMORY, key="editor", content="Visual Studio Code", tags=["code"])
    mgr.add_memory(MemoryType.PROJECT_MEMORY, key="database", content="SQLite local file", tags=["db"])

    # Query matching browser
    results = mgr.retrieve_relevant("Which browser do I prefer?")
    assert len(results) > 0
    top_item, score = results[0]
    assert top_item.key == "browser"
    assert top_item.content == "Google Chrome"

    # Query matching editor
    results = mgr.retrieve_relevant("Open my coding editor")
    assert len(results) > 0
    top_item, score = results[0]
    assert top_item.key == "editor"


# ============================================================================
# 3. CONFLICT HANDLING AND RESOLUTION TESTS
# ============================================================================

def test_conflict_handling_overrides_stale_preference(tmp_path):
    """Verify add_memory seamlessly updates content under the same key without duplicate contradiction."""
    store_file = tmp_path / "test_memory.json"
    mgr = MemoryManager(storage_path=str(store_file))

    # Initial preference
    m1 = mgr.add_memory(MemoryType.PREFERENCE_MEMORY, key="default_browser", content="Microsoft Edge")
    id1 = m1.id

    # User changes preference
    m2 = mgr.add_memory(MemoryType.PREFERENCE_MEMORY, key="default_browser", content="Google Chrome")
    assert m2.id == id1, "Should update the same memory item to prevent duplicate contradiction"
    assert m2.content == "Google Chrome"

    # Verify only 1 memory item exists
    all_prefs = mgr.view_all_memories(MemoryType.PREFERENCE_MEMORY)
    assert len(all_prefs) == 1
    assert all_prefs[0]["content"] == "Google Chrome"


# ============================================================================
# 4. USER CONTROLS (View, Delete, Correct, Disable)
# ============================================================================

def test_user_memory_controls(tmp_path):
    """Verify user controls: View, Correct, Delete, and Disable."""
    store_file = tmp_path / "test_memory.json"
    mgr = MemoryManager(storage_path=str(store_file))

    item = mgr.add_memory(MemoryType.LONG_TERM_MEMORY, key="city", content="New Delhi")
    m_id = item.id

    # 1. View
    all_m = mgr.view_all_memories()
    assert len(all_m) == 1

    # 2. Correct
    corrected = mgr.correct_memory(m_id, "Mumbai")
    assert corrected is True
    assert mgr.view_all_memories()[0]["content"] == "Mumbai"

    # 3. Disable
    mgr.set_enabled(False)
    assert mgr.is_enabled() is False
    # When disabled, additions are non-persisted stubs
    stub = mgr.add_memory(MemoryType.PREFERENCE_MEMORY, key="theme", content="dark")
    assert stub.id == "disabled"
    assert len(mgr.view_all_memories()) == 1  # unchanged

    # 4. Re-enable & Delete
    mgr.set_enabled(True)
    deleted = mgr.delete_memory(m_id)
    assert deleted is True
    assert len(mgr.view_all_memories()) == 0


# ============================================================================
# 5. CROSS-SESSION PERSISTENCE TESTS
# ============================================================================

def test_cross_session_persistence(tmp_path):
    """Verify memories survive reload from disk storage."""
    store_file = tmp_path / "persisted_memory.json"
    
    # Session 1: write
    mgr1 = MemoryManager(storage_path=str(store_file))
    mgr1.add_memory(MemoryType.PROJECT_MEMORY, key="project_name", content="SPR SAATHI")
    mgr1.record_conversation_turn("user", "Hello session 1")

    # Session 2: reload from same file
    mgr2 = MemoryManager(storage_path=str(store_file))
    memories = mgr2.view_all_memories()
    assert len(memories) == 1
    assert memories[0]["key"] == "project_name"
    assert memories[0]["content"] == "SPR SAATHI"

    history = mgr2.get_conversation_history()
    assert len(history) == 1
    assert history[0]["message"] == "Hello session 1"
