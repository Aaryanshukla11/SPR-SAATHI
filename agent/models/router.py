import os
import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

from .base import BaseModelProvider, ModelResponse
from .local import LocalModelProvider
from .api import ApiModelProvider

logger = logging.getLogger("agent.models.router")


class ModelCapability(str, Enum):
    VISION = "vision"
    CODING = "coding"
    REASONING = "reasoning"
    FAST = "fast"
    LOCAL = "local"


class PrivacyLevel(str, Enum):
    LOCAL_ONLY = "local_only"
    ANY = "any"


@dataclass
class ModelSpec:
    name: str
    provider_type: str  # "local" or "api"
    capabilities: List[ModelCapability]
    cost_tier: str = "free"  # "free", "low", "medium", "high"
    speed_tier: str = "medium"  # "fast", "medium", "thorough"
    is_available: bool = True
    failure_count: int = 0


class ModelRouter:
    """
    Phase 11: Multi-Model Intelligence and Routing Engine.
    
    Dynamically routes requests across local and cloud providers based on:
    - Task complexity & reasoning requirements
    - Vision requirements (images attached)
    - Coding specialization
    - Privacy boundaries (local-only constraints)
    - Speed vs Cost tradeoffs
    - Automatic failover & graceful fallback on provider errors
    """

    def __init__(self, default_provider: Optional[BaseModelProvider] = None):
        self._models: Dict[str, Tuple[ModelSpec, BaseModelProvider]] = {}
        self.default_provider = default_provider
        self.local_preferred = False
        self._init_default_models()

    def _init_default_models(self):
        """Initializes default catalog specs."""
        # 1. Fast cloud model
        gemini_spec = ModelSpec(
            name="gemini-2.5-flash",
            provider_type="api",
            capabilities=[ModelCapability.FAST, ModelCapability.VISION, ModelCapability.REASONING],
            cost_tier="low",
            speed_tier="fast"
        )
        self.register_model(gemini_spec, ApiModelProvider(model_name="Gemini 3.5 Flash"))

        # 2. Local Ollama model
        ollama_spec = ModelSpec(
            name="qwen2.5:latest",
            provider_type="local",
            capabilities=[ModelCapability.LOCAL, ModelCapability.CODING, ModelCapability.REASONING],
            cost_tier="free",
            speed_tier="medium"
        )
        self.register_model(ollama_spec, LocalModelProvider(model_name="qwen2.5:latest"))

        # 3. Local Vision model
        ollama_vision_spec = ModelSpec(
            name="llama3.2-vision:latest",
            provider_type="local",
            capabilities=[ModelCapability.LOCAL, ModelCapability.VISION],
            cost_tier="free",
            speed_tier="medium"
        )
        self.register_model(ollama_vision_spec, LocalModelProvider(model_name="llama3.2-vision:latest"))

    def register_model(self, spec: ModelSpec, provider: BaseModelProvider):
        self._models[spec.name] = (spec, provider)

    def route(
        self,
        task: str,
        has_image: bool = False,
        privacy_level: PrivacyLevel = PrivacyLevel.ANY,
        force_provider: Optional[str] = None
    ) -> Tuple[BaseModelProvider, ModelSpec]:
        """
        Determines the optimal model provider for the given task.
        """
        task_lower = task.lower()
        q_tokens = set(re.findall(r"\w+", task_lower))

        # Check coding indicators
        is_coding = bool(
            {"python", "code", "script", "function", "debug", "refactor", "bug", "algorithm", "def", "class"} & q_tokens
        )
        # Check complex reasoning indicators
        is_complex = bool(
            {"architect", "decompose", "multi-step", "strategy", "comprehensive", "plan", "analyze"} & q_tokens
        )
        # Check privacy or local constraints
        must_be_local = (privacy_level == PrivacyLevel.LOCAL_ONLY) or self.local_preferred

        candidates = []
        for name, (spec, prov) in self._models.items():
            if not spec.is_available:
                continue

            # Check force_provider constraint
            if force_provider and spec.provider_type != force_provider.lower():
                continue

            # Check privacy constraint
            if must_be_local and spec.provider_type != "local":
                continue

            # Check vision constraint
            if has_image and ModelCapability.VISION not in spec.capabilities:
                continue

            score = 10.0
            if has_image and ModelCapability.VISION in spec.capabilities:
                score += 15.0
            if is_coding and ModelCapability.CODING in spec.capabilities:
                score += 8.0
            if is_complex and ModelCapability.REASONING in spec.capabilities:
                score += 5.0
            if not is_complex and not has_image and ModelCapability.FAST in spec.capabilities:
                score += 4.0

            # Penalize recent failures
            score -= spec.failure_count * 5.0

            candidates.append((score, prov, spec))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_prov, best_spec = candidates[0]
            logger.info(f"ModelRouter selected: {best_spec.name} (Score: {best_score})")
            return best_prov, best_spec

        # Fallback to default provider or first registered model
        if self.default_provider:
            return self.default_provider, ModelSpec(name="default", provider_type="custom", capabilities=[])
        
        first_name = next(iter(self._models))
        spec, prov = self._models[first_name]
        return prov, spec

    async def generate_with_fallback(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        privacy_level: PrivacyLevel = PrivacyLevel.ANY,
        max_fallbacks: int = 2
    ) -> ModelResponse:
        """
        Executes generation with automatic failover to healthy alternatives if primary provider fails.
        """
        attempted_specs = set()
        has_image = image_bytes is not None

        for attempt in range(max_fallbacks + 1):
            prov, spec = self.route(
                task=prompt,
                has_image=has_image,
                privacy_level=privacy_level
            )

            # Avoid re-attempting failed spec in same cycle
            if spec.name in attempted_specs:
                break

            attempted_specs.add(spec.name)

            try:
                logger.info(f"Attempting model generation via: {spec.name}")
                response = await prov.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    image_bytes=image_bytes
                )
                spec.failure_count = max(0, spec.failure_count - 1)
                return response
            except Exception as e:
                logger.warning(f"Provider {spec.name} failed: {e}. Attempting failover...")
                spec.failure_count += 1
                if attempt == max_fallbacks:
                    raise RuntimeError(f"All model providers failed. Last error: {e}") from e

        raise RuntimeError("No available model providers succeeded.")


# Global singleton instance
MODEL_ROUTER = ModelRouter()
