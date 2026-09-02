import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from agent.main import app, state_tracker
from agent.models.base import ModelResponse

@pytest.fixture
def client():
    return TestClient(app)

def test_chat_endpoint_basic(client):
    """Test Chatbot Mode /api/chat returns conversational response without invoking agent tools."""
    mock_resp = ModelResponse(text="Hello! I am SPR SAATHI in Chatbot Mode. How can I help you today?")
    
    with patch("agent.main.current_model_provider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        
        res = client.post("/api/chat", json={"message": "Hello, how are you?"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "Hello! I am SPR SAATHI" in data["response"]
        
        # Verify generate was called with conversation text and system instruction
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["prompt"] == "Hello, how are you?"
        assert "Chatbot Mode" in call_kwargs["system_instruction"]

def test_chat_endpoint_with_history(client):
    """Test Chatbot Mode preserves multi-turn conversation history."""
    mock_resp = ModelResponse(text="A binary search algorithm has O(log n) time complexity.")
    
    with patch("agent.main.current_model_provider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        
        history = [
            {"role": "user", "content": "What is binary search?"},
            {"role": "assistant", "content": "Binary search is an efficient search algorithm on sorted arrays."}
        ]
        res = client.post("/api/chat", json={
            "message": "What is its time complexity?",
            "history": history
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "O(log n)" in data["response"]
        
        call_kwargs = mock_gen.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "User: What is binary search?" in prompt
        assert "Assistant: Binary search" in prompt
        assert "User: What is its time complexity?" in prompt

def test_chat_clear_endpoint(client):
    """Test /api/chat/clear endpoint successfully clears conversation context."""
    res = client.post("/api/chat/clear")
    assert res.status_code == 200
    assert res.json()["status"] == "cleared"

def test_mode_separation_chat_does_not_mutate_agent_state(client):
    """Ensure Chatbot mode does not change state_tracker status from idle or start agent loop."""
    initial_status = state_tracker.status
    mock_resp = ModelResponse(text="Here is a Python function: def add(a, b): return a + b")
    
    with patch("agent.main.current_model_provider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_resp
        res = client.post("/api/chat", json={"message": "Write a Python add function"})
        assert res.status_code == 200
        
        # State tracker status should NOT change to 'acting' or 'planning'
        assert state_tracker.status == initial_status
