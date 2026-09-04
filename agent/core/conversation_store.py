"""
Persistent Conversation Store for SPR SAATHI.

Manages multi-session conversation histories with disk persistence (JSON),
atomic file updates, metadata indexing, and auto-titling for both Chatbot Mode
and agent interaction records.
"""

import os
import json
import uuid
import datetime
import threading
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("agent.conversation_store")


class ConversationStore:
    """Manages persistent multi-session conversation histories."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path:
            self.storage_path = storage_path
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.storage_path = os.path.join(base_dir, "data", "conversations.json")

        self._lock = threading.Lock()
        self._conversations: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Loads conversations from disk storage."""
        if os.path.exists(self.storage_path) and os.path.getsize(self.storage_path) > 0:
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._conversations = data.get("conversations", {})
            except Exception as e:
                logger.error(f"Failed to load conversations from {self.storage_path}: {e}")
                self._conversations = {}

    def _save(self):
        """Persists conversations atomically to disk."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            payload = {
                "version": "1.0",
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "conversations": self._conversations
            }
            tmp_path = f"{self.storage_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.storage_path)
        except Exception as e:
            logger.error(f"Failed to persist conversation store to {self.storage_path}: {e}")

    @staticmethod
    def _generate_title_from_text(text: str) -> str:
        """Derives a clean, concise conversation title from the first message."""
        cleaned = " ".join(text.strip().split())
        # Strip common prompt prefixes in a loop
        changed = True
        while changed:
            changed = False
            for prefix in ["please ", "can you ", "could you ", "how to ", "how do i ", "how ", "what is ", "explain ", "tell me about ", "tell me "]:
                if cleaned.lower().startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
                    changed = True
                    break
        if not cleaned:
            return "New Conversation"
        # Truncate to reasonable title length
        if len(cleaned) > 42:
            cleaned = cleaned[:40].rstrip() + "..."
        return cleaned[:1].upper() + cleaned[1:]

    def list_conversations(self) -> List[Dict[str, Any]]:
        """
        Returns a list of conversation summaries sorted by most recently updated first.
        """
        with self._lock:
            summaries = []
            for c_id, conv in self._conversations.items():
                messages = conv.get("messages", [])
                last_msg = messages[-1]["content"] if messages else ""
                snippet = (last_msg[:90] + "...") if len(last_msg) > 90 else last_msg
                summaries.append({
                    "id": c_id,
                    "title": conv.get("title", "Conversation"),
                    "created_at": conv.get("created_at"),
                    "updated_at": conv.get("updated_at"),
                    "model": conv.get("model", "unknown"),
                    "message_count": len(messages),
                    "snippet": snippet
                })
            summaries.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
            return summaries

    def get_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Returns the full conversation including all messages, or None if not found."""
        with self._lock:
            conv = self._conversations.get(session_id)
            if conv:
                return json.loads(json.dumps(conv))
            return None

    def create_conversation(
        self,
        title: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates and persists a new conversation session."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        s_id = session_id or f"conv_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
        conv = {
            "id": s_id,
            "title": title or "New Conversation",
            "created_at": now,
            "updated_at": now,
            "model": model or "unknown",
            "messages": []
        }
        with self._lock:
            self._conversations[s_id] = conv
            self._save()
        return conv

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        model: Optional[str] = None,
        msg_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Appends a message to an existing conversation, or auto-creates the session if not present.
        If it's the first user message, automatically generates a descriptive title.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        m_id = msg_id or f"msg_{int(datetime.datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:4]}"
        message_obj = {
            "id": m_id,
            "role": role,
            "content": content,
            "timestamp": now
        }

        with self._lock:
            if session_id not in self._conversations:
                # Auto-create session
                title = self._generate_title_from_text(content) if role == "user" else "New Conversation"
                self._conversations[session_id] = {
                    "id": session_id,
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "model": model or "unknown",
                    "messages": [message_obj]
                }
            else:
                conv = self._conversations[session_id]
                conv["messages"].append(message_obj)
                conv["updated_at"] = now
                if model:
                    conv["model"] = model
                # If title was generic and user sends their first message, improve title
                if conv.get("title") in ["New Conversation", "Conversation"] and role == "user":
                    conv["title"] = self._generate_title_from_text(content)

            self._save()
            return message_obj

    def update_title(self, session_id: str, new_title: str) -> bool:
        """Updates the title of a conversation session."""
        with self._lock:
            if session_id in self._conversations:
                self._conversations[session_id]["title"] = new_title.strip() or "Untitled Conversation"
                self._conversations[session_id]["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self._save()
                return True
            return False

    def delete_conversation(self, session_id: str) -> bool:
        """Deletes a conversation session by ID."""
        with self._lock:
            if session_id in self._conversations:
                del self._conversations[session_id]
                self._save()
                return True
            return False

    def clear_all(self):
        """Clears all conversation records."""
        with self._lock:
            self._conversations.clear()
            self._save()


# Global singleton instance
CONVERSATION_STORE = ConversationStore()
