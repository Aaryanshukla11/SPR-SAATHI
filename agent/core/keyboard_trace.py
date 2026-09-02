import hashlib
import time
from typing import Dict, Any, List, Optional

class KeyboardTraceLogger:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.action_counts: Dict[str, int] = {}
        self.type_text_counts: Dict[str, int] = {}

    def clear(self):
        self.events.clear()
        self.action_counts.clear()
        self.type_text_counts.clear()

    def record_tool_call(self, call_id: str, text: str) -> Dict[str, Any]:
        cid = call_id or "anonymous"
        self.action_counts[cid] = self.action_counts.get(cid, 0) + 1
        checksum = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        event = {
            "type": "keyboard_type_tool_received",
            "timestamp": time.time(),
            "call_id": cid,
            "call_count_for_id": self.action_counts[cid],
            "text_length": len(text),
            "sha256": checksum,
            "text_preview": text[:60] if len(text) > 60 else text
        }
        self.events.append(event)
        return event

    def record_type_text_start(self, call_id: str, text: str, chunk_size: int = 1, typing_path: str = "win32_clipboard_paste") -> Dict[str, Any]:
        cid = call_id or "anonymous"
        self.type_text_counts[cid] = self.type_text_counts.get(cid, 0) + 1
        checksum = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        event = {
            "type": "type_text_invoked",
            "timestamp": time.time(),
            "call_id": cid,
            "invocation_count_for_id": self.type_text_counts[cid],
            "text_length": len(text),
            "chunk_size": chunk_size,
            "typing_path": typing_path,
            "sha256": checksum,
            "text_preview": text[:60] if len(text) > 60 else text
        }
        self.events.append(event)
        return event

    def record_type_text_completed(
        self,
        call_id: str,
        text: str,
        typing_path: str,
        target_hwnd: Optional[int],
        target_title: Optional[str],
        clipboard_restored: bool,
        duration_ms: float,
        retried: bool = False
    ) -> Dict[str, Any]:
        cid = call_id or "anonymous"
        checksum = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        event = {
            "type": "type_text_completed",
            "timestamp": time.time(),
            "call_id": cid,
            "invocation_count_for_id": self.type_text_counts.get(cid, 1),
            "text_length": len(text),
            "sha256": checksum,
            "typing_path": typing_path,
            "target_hwnd": target_hwnd,
            "target_title": target_title,
            "clipboard_restored": clipboard_restored,
            "duration_ms": duration_ms,
            "retried": retried
        }
        self.events.append(event)
        return event

    def get_traces_for_call_id(self, call_id: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e.get("call_id") == call_id]

    def get_last_trace(self) -> Optional[Dict[str, Any]]:
        return self.events[-1] if self.events else None

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_events": len(self.events),
            "unique_call_ids": list(self.action_counts.keys()),
            "type_text_invocations": self.type_text_counts
        }

KEYBOARD_TRACER = KeyboardTraceLogger()
