import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.models.router import (
    ModelRouter, ModelSpec, ModelCapability, PrivacyLevel
)
from agent.models.base import BaseModelProvider, ModelResponse


class MockProvider(BaseModelProvider):
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail

    async def generate(self, prompt, system_instruction=None, image_bytes=None):
        if self.should_fail:
            raise RuntimeError(f"Connection failed to {self.name}")
        return ModelResponse(text=f"Response from {self.name}")

    async def decide_action(self, prompt, system_instruction=None, image_bytes=None, tools=None):
        return await self.generate(prompt, system_instruction, image_bytes)

    async def generate_with_tools(self, prompt, tools, system_instruction=None, image_bytes=None):
        return await self.generate(prompt, system_instruction, image_bytes)


# ============================================================================
# 1. ROUTING ACCURACY TESTS
# ============================================================================

def test_routing_accuracy_vision_task():
    """Verify tasks with image requirements route to vision-capable models."""
    router = ModelRouter()
    prov, spec = router.route("Analyze this chart image", has_image=True)
    assert ModelCapability.VISION in spec.capabilities


def test_routing_accuracy_coding_task():
    """Verify coding tasks prioritize models with coding capabilities."""
    router = ModelRouter()
    prov, spec = router.route("Write a python function to parse JSON files", has_image=False)
    assert ModelCapability.CODING in spec.capabilities


def test_routing_accuracy_privacy_local_task():
    """Verify privacy-constrained tasks route exclusively to local models."""
    router = ModelRouter()
    prov, spec = router.route(
        "Analyze confidential private spreadsheet",
        privacy_level=PrivacyLevel.LOCAL_ONLY
    )
    assert spec.provider_type == "local"
    assert ModelCapability.LOCAL in spec.capabilities


# ============================================================================
# 2. LOCAL / CLOUD SWITCHING
# ============================================================================

def test_local_cloud_switching_preference():
    """Verify switching local_preferred shifts routing to local hardware."""
    router = ModelRouter()
    router.local_preferred = True

    prov, spec = router.route("General query")
    assert spec.provider_type == "local"

    router.local_preferred = False
    prov_cloud, spec_cloud = router.route("General query")
    assert spec_cloud.provider_type == "api"


# ============================================================================
# 3. PROVIDER FAILURE AND AUTOMATIC FALLBACK
# ============================================================================

@pytest.mark.asyncio
async def test_provider_failure_and_fallback():
    """Verify that when primary provider fails, ModelRouter automatically fails over to backup."""
    router = ModelRouter()
    router._models.clear()

    # Primary model that will fail
    p1 = MockProvider("Primary-API", should_fail=True)
    s1 = ModelSpec("primary_cloud", "api", [ModelCapability.FAST], failure_count=0)
    router.register_model(s1, p1)

    # Backup model that succeeds
    p2 = MockProvider("Backup-Local", should_fail=False)
    s2 = ModelSpec("backup_local", "local", [ModelCapability.LOCAL], failure_count=0)
    router.register_model(s2, p2)

    resp = await router.generate_with_fallback("Hello test", max_fallbacks=1)
    assert "Response from Backup-Local" in resp.text
    assert s1.failure_count > 0, "Failed model failure count should be incremented"
