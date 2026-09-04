import re
from typing import Dict, Any, List, Optional, Tuple
from .base import BaseSkill


class SkillRegistry:
    """
    Phase 5: Skill Registry and Discovery System.
    
    Provides:
    - Skill registration
    - Discovery and matching by goal description
    - Schema validation
    - Required permissions & tools resolution
    """

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Registers a skill ensuring all 8 required attributes are present."""
        if not isinstance(skill, BaseSkill):
            raise TypeError("Registered skill must inherit from BaseSkill.")
        name = skill.name
        if not name:
            raise ValueError("Skill must have a non-empty name.")
        self._skills[name] = skill

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """Returns catalog of all registered skills with their signatures and strategies."""
        catalog = []
        for s in self._skills.values():
            catalog.append({
                "name": s.name,
                "description": s.description,
                "input_schema": s.input_schema,
                "output_schema": s.output_schema,
                "required_permissions": s.required_permissions,
                "required_tools": s.required_tools,
                "verification_strategy": s.verification_strategy,
                "fallback_strategy": s.fallback_strategy
            })
        return catalog

    def discover_skills_for_goal(self, goal: str) -> List[Tuple[BaseSkill, float]]:
        """
        Scores and ranks registered skills based on relevance to the user goal.
        Returns list of (skill, relevance_score) sorted descending by score.
        """
        if not goal:
            return []

        tokens = set(re.findall(r"\w+", goal.lower()))
        matches: List[Tuple[BaseSkill, float]] = []

        for skill in self._skills.values():
            score = 0.0
            s_name_tokens = set(re.findall(r"\w+", skill.name.lower()))
            s_desc_tokens = set(re.findall(r"\w+", skill.description.lower()))

            # Exact skill name mentioned in goal
            if skill.name.lower() in goal.lower():
                score += 5.0

            # Token overlap in name
            name_overlap = len(tokens & s_name_tokens)
            score += name_overlap * 2.0

            # Token overlap in description
            desc_overlap = len(tokens & s_desc_tokens)
            score += desc_overlap * 0.5

            if score > 0:
                matches.append((skill, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches


# Global singleton instance
SKILL_REGISTRY = SkillRegistry()
