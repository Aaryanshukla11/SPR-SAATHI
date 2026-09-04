import pytest
import os
import tempfile
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from agent.core.conversation_store import ConversationStore
from agent.main import app
from agent.models.base import ModelResponse

@pytest.fixture
def temp_store():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = f.name
    store = ConversationStore(storage_path=tmp_path)
    yield store
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    if os.path.exists(f"{tmp_path}.tmp"):
        os.remove(f"{tmp_path}.tmp")

@pytest.fixture
def client():
    return TestClient(app)

def test_conversation_store_create_and_list(temp_store):
    conv = temp_store.create_conversation(title="Test Chat", model="Qwen 2.5 7B")
    assert conv["id"].startswith("conv_")
    assert conv["title"] == "Test Chat"
    assert conv["model"] == "Qwen 2.5 7B"
    assert conv["messages"] == []

    summaries = temp_store.list_conversations()
    assert len(summaries) == 1
    assert summaries[0]["id"] == conv["id"]
    assert summaries[0]["title"] == "Test Chat"
    assert summaries[0]["message_count"] == 0

def test_conversation_store_append_and_persistence(temp_store):
    conv = temp_store.create_conversation(title="Python Help")
    s_id = conv["id"]

    msg1 = temp_store.append_message(s_id, "user", "How do I write a decorator?")
    assert msg1["role"] == "user"
    assert msg1["content"] == "How do I write a decorator?"

    msg2 = temp_store.append_message(s_id, "assistant", "Use def my_decorator(func): ...")
    assert msg2["role"] == "assistant"

    fetched = temp_store.get_conversation(s_id)
    assert fetched is not None
    assert len(fetched["messages"]) == 2

    # Verify atomic disk persistence
    reloaded_store = ConversationStore(storage_path=temp_store.storage_path)
    reloaded_conv = reloaded_store.get_conversation(s_id)
    assert reloaded_conv is not None
    assert len(reloaded_conv["messages"]) == 2
    assert reloaded_conv["messages"][0]["content"] == "How do I write a decorator?"

def test_conversation_store_auto_title_generation(temp_store):
    # Auto-creating conversation on first message
    s_id = "test_auto_title"
    temp_store.append_message(s_id, "user", "Please explain how quicksort works in detail")
    conv = temp_store.get_conversation(s_id)
    assert conv is not None
    assert "quicksort works in detail" in conv["title"].lower()

def test_conversation_store_delete_and_clear(temp_store):
    c1 = temp_store.create_conversation(title="Chat 1")
    c2 = temp_store.create_conversation(title="Chat 2")
    assert len(temp_store.list_conversations()) == 2

    ok = temp_store.delete_conversation(c1["id"])
    assert ok is True
    assert len(temp_store.list_conversations()) == 1
    assert temp_store.get_conversation(c1["id"]) is None

    temp_store.clear_all()
    assert len(temp_store.list_conversations()) == 0

def test_api_conversation_endpoints(client):
    # 1. Create conversation via API
    res = client.post("/api/conversations", json={"title": "REST API Test", "model": "TestModel"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "created"
    session_id = data["conversation"]["id"]

    # 2. List conversations
    res = client.get("/api/conversations")
    assert res.status_code == 200
    convs = res.json()["conversations"]
    assert any(c["id"] == session_id for c in convs)

    # 3. Get specific conversation
    res = client.get(f"/api/conversations/{session_id}")
    assert res.status_code == 200
    assert res.json()["conversation"]["title"] == "REST API Test"

    # 4. Update title
    res = client.patch(f"/api/conversations/{session_id}", json={"title": "Renamed API Test"})
    assert res.status_code == 200
    res = client.get(f"/api/conversations/{session_id}")
    assert res.json()["conversation"]["title"] == "Renamed API Test"

    # 5. Delete conversation
    res = client.delete(f"/api/conversations/{session_id}")
    assert res.status_code == 200
    res = client.get(f"/api/conversations/{session_id}")
    assert res.status_code == 404

def test_chat_endpoint_preserves_session_id(client):
    import uuid
    mock_resp = ModelResponse(text="Here is your answer about React hooks.")

    with patch("agent.main.current_model_provider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp

        # Send chat with unique session_id
        session_id = f"test_session_{uuid.uuid4().hex[:8]}"
        res = client.post("/api/chat", json={
            "message": "Explain useEffect in React",
            "session_id": session_id
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["session_id"] == session_id

        # Verify conversation was saved in store
        conv_res = client.get(f"/api/conversations/{session_id}")
        assert conv_res.status_code == 200
        conv_data = conv_res.json()["conversation"]
        assert len(conv_data["messages"]) == 2
        assert conv_data["messages"][0]["role"] == "user"
        assert conv_data["messages"][0]["content"] == "Explain useEffect in React"
        assert conv_data["messages"][1]["role"] == "assistant"
        assert "React hooks" in conv_data["messages"][1]["content"]

        # Clean up test session
        client.delete(f"/api/conversations/{session_id}")
