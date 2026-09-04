from .base import BaseSkill, SkillExecutionResult
from .registry import SkillRegistry, SKILL_REGISTRY
from .file_organizer import OrganizeFilesSkill
from .document_creator import CreateDocumentSkill
from .data_analysis import AnalyzeDatasetSkill
from .research import ResearchTopicSkill


def get_skill_registry() -> SkillRegistry:
    """Returns the globally populated skill registry."""
    if not SKILL_REGISTRY.list_skills():
        SKILL_REGISTRY.register(OrganizeFilesSkill())
        SKILL_REGISTRY.register(CreateDocumentSkill())
        SKILL_REGISTRY.register(AnalyzeDatasetSkill())
        SKILL_REGISTRY.register(ResearchTopicSkill())
    return SKILL_REGISTRY


# Initialize default skills immediately
get_skill_registry()
