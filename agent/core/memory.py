import os
import json
import uuid
import re
import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger("agent.core.memory")


class MemoryType(str, Enum):
    CONVERSATION_HISTORY = "conversation_history"
    SHORT_TERM_CONTEXT = "short_term_context"
    LONG_TERM_MEMORY = "long_term_memory"
    PREFERENCE_MEMORY = "preference_memory"
    PROJECT_MEMORY = "project_memory"


@dataclass
class MemoryItem:
    id: str
    memory_type: MemoryType
    key: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    source: str = "user"
    confidence: float = 1.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "key": self.key,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
            "confidence": self.confidence,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            id=data["id"],
            memory_type=MemoryType(data["memory_type"]),
            key=data["key"],
            content=data["content"],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            source=data.get("source", "user"),
            confidence=float(data.get("confidence", 1.0)),
            tags=data.get("tags", [])
        )


class MemoryManager:
    """
    Phase 8: Memory and Conversation Intelligence Engine.
    
    Provides:
    - 5 Memory Tiers: Conversation, Short-Term, Long-Term, Preference, Project
    - Semantic / Keyword relevance retrieval
    - Conflict resolution (updates & overrides)
    - Full user controls: View, Delete, Correct, Disable
    - Cross-session JSON persistence
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self.storage_path = os.path.abspath(storage_path)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.storage_path = os.path.join(base_dir, "data", "memory_store.json")

        self._enabled: bool = True
        self._memories: Dict[str, MemoryItem] = {}
        self._conversations: List[Dict[str, Any]] = []
        self._load()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def _load(self):
        """Loads persisted memories from JSON disk storage."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._enabled = data.get("enabled", True)
                    self._conversations = data.get("conversations", [])
                    raw_items = data.get("memories", {})
                    for m_id, item_data in raw_items.items():
                        try:
                            self._memories[m_id] = MemoryItem.from_dict(item_data)
                        except Exception as e:
                            logger.warning(f"Failed to deserialize memory {m_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to load memory store from {self.storage_path}: {e}")

    def _save(self):
        """Persists memories atomically to disk."""
        if not self._enabled:
            return
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            payload = {
                "version": "1.0",
                "enabled": self._enabled,
                "conversations": self._conversations[-200:],  # retain last 200 turns
                "memories": {m_id: item.to_dict() for m_id, item in self._memories.items()}
            }
            tmp_path = f"{self.storage_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.storage_path)
        except Exception as e:
            logger.error(f"Failed to persist memory store: {e}")

    def add_memory(
        self,
        memory_type: MemoryType,
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        source: str = "user"
    ) -> MemoryItem:
        """
        Creates or updates a memory item. If an item with the same key and type exists,
        it updates the content cleanly (conflict resolution).
        """
        if not self._enabled:
            return MemoryItem(id="disabled", memory_type=memory_type, key=key, content=content)

        # Check for existing memory with the same type and key
        existing = None
        for m in self._memories.values():
            if m.memory_type == memory_type and m.key.lower() == key.lower():
                existing = m
                break

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if existing:
            # Update existing memory item (conflict override)
            existing.content = content
            existing.updated_at = now_str
            existing.metadata.update(metadata or {})
            if tags:
                existing.tags = list(set(existing.tags + tags))
            self._save()
            return existing
        else:
            new_id = f"mem_{uuid.uuid4().hex[:10]}"
            item = MemoryItem(
                id=new_id,
                memory_type=memory_type,
                key=key,
                content=content,
                metadata=metadata or {},
                created_at=now_str,
                updated_at=now_str,
                source=source,
                tags=tags or []
            )
            self._memories[new_id] = item
            self._save()
            return item

    def record_conversation_turn(self, role: str, message: str, session_id: Optional[str] = None):
        """Records a conversational turn."""
        if not self._enabled:
            return
        turn = {
            "role": role,
            "message": message,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": session_id or "default"
        }
        self._conversations.append(turn)
        self._save()

    def get_conversation_history(self, limit: int = 20, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves conversational turns."""
        turns = self._conversations
        if session_id:
            turns = [t for t in turns if t.get("session_id") == session_id]
        return turns[-limit:]

    def retrieve_relevant(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 5
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Scores memories by keyword & token relevance to query.
        Returns list of (MemoryItem, score) sorted descending.
        """
        if not self._enabled or not query:
            return []

        q_tokens = set(re.findall(r"\w+", query.lower()))
        matches: List[Tuple[MemoryItem, float]] = []

        for m in self._memories.values():
            if memory_types and m.memory_type not in memory_types:
                continue

            score = 0.0
            key_tokens = set(re.findall(r"\w+", m.key.lower()))
            content_tokens = set(re.findall(r"\w+", m.content.lower()))
            tag_tokens = {t.lower() for t in m.tags}

            # Exact key match
            if m.key.lower() in query.lower():
                score += 5.0

            # Token overlap in key
            score += len(q_tokens & key_tokens) * 3.0

            # Token overlap in content
            score += len(q_tokens & content_tokens) * 1.0

            # Tag overlap
            score += len(q_tokens & tag_tokens) * 2.5

            if score > 0:
                matches.append((m, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    # User Controls (Phase 8 Requirement: View, Delete, Correct, Disable)
    def view_all_memories(self, memory_type: Optional[MemoryType] = None) -> List[Dict[str, Any]]:
        """Lists memories for user inspection."""
        items = list(self._memories.values())
        if memory_type:
            items = [m for m in items if m.memory_type == memory_type]
        return [m.to_dict() for m in items]

    def delete_memory(self, memory_id: str) -> bool:
        """Deletes a memory item by ID."""
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._save()
            return True
        return False

    def correct_memory(self, memory_id: str, new_content: str) -> bool:
        """Corrects/replaces content of a memory item."""
        if memory_id in self._memories:
            item = self._memories[memory_id]
            item.content = new_content
            item.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return True
        return False

    def clear_all(self):
        """Clears all stored memories."""
        self._memories.clear()
        self._conversations.clear()
        self._save()


# Global singleton instance
MEMORY_MANAGER = MemoryManager()
