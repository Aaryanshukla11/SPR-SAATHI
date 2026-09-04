import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from agent.main import app, MEMORY_MANAGER, WORKSPACE_MANAGER, SKILL_REGISTRY
from agent.core.memory import MemoryType
from agent.core.workspace import FileOrigin


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================================
# 1. MEMORY ENDPOINTS
# ============================================================================

def test_memory_crud_endpoints(client):
    # Store memory
    res = client.post("/api/memory", json={
        "key": "test_preference",
        "content": "User prefers concise responses",
        "memory_type": "preference_memory",
        "tags": ["style", "test"]
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    mem_id = data["memory"]["id"]
    assert data["memory"]["key"] == "test_preference"

    # List memories
    res = client.get("/api/memory?type=preference_memory")
    assert res.status_code == 200
    mems = res.json()
    assert any(m["id"] == mem_id for m in mems)

    # Search memories
    res = client.post("/api/memory/search", json={"query": "concise responses", "limit": 3})
    assert res.status_code == 200
    search_results = res.json()
    assert len(search_results) > 0
    assert any(r["memory"]["id"] == mem_id for r in search_results)

    # Delete memory
    res = client.delete(f"/api/memory/{mem_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "deleted"


# ============================================================================
# 2. WORKSPACE ENDPOINTS
# ============================================================================

def test_workspace_endpoints(client):
    # List workspace files
    res = client.get("/api/workspace/files")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Search workspace files
    res = client.get("/api/workspace/search?query=main.py&limit=5")
    assert res.status_code == 200
    results = res.json()
    assert isinstance(results, list)


# ============================================================================
# 3. SKILLS ENDPOINTS
# ============================================================================

def test_skills_catalog_and_execution_endpoints(client):
    # List skills
    res = client.get("/api/skills")
    assert res.status_code == 200
    skills = res.json()
    assert len(skills) >= 4
    skill_names = [s["name"] for s in skills]
    assert "create_document" in skill_names
    assert "analyze_dataset" in skill_names
    assert "organize_files" in skill_names
    assert "research_topic" in skill_names

    # Test non-existent skill returns 404
    res = client.post("/api/skills/non_existent_skill_xyz/execute", json={"parameters": {}})
    assert res.status_code == 404


# ============================================================================
# 4. SPECIALISTS ENDPOINTS
# ============================================================================

def test_specialists_endpoints(client):
    # List specialists
    res = client.get("/api/specialists")
    assert res.status_code == 200
    specs = res.json()
    spec_names = [s["name"] for s in specs]
    assert any("KAIRO-AI" in name for name in spec_names)

    # Delegate coding task to KAIRO-AI
    res = client.post("/api/specialists/delegate", json={
        "task": "Write a python function to compute factorial"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["verification_passed"] is True
    assert "solution.py" in data["code_artifacts"]


# ============================================================================
# 5. OBSERVABILITY TRACE ENDPOINTS
# ============================================================================

def test_trace_endpoints(client):
    res = client.get("/api/trace")
    assert res.status_code == 200
    assert "steps" in res.json()

    res = client.get("/api/trace/summary")
    assert res.status_code == 200


# ============================================================================
# 6. SYSTEM METRICS & HEALTH ENDPOINTS
# ============================================================================

def test_system_metrics_endpoint(client):
    res = client.get("/api/system/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "memory" in data
    assert "rss_mb" in data["memory"]
    assert "system" in data
    assert "cpu_percent" in data["system"]
    assert "agent" in data
    assert "status" in data["agent"]


# ============================================================================
# 7. MODEL CATALOG ENDPOINT
# ============================================================================

def test_model_catalog_endpoint(client):
    res = client.get("/api/models/catalog")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert len(data["models"]) >= 2
    assert "active_model" in data
