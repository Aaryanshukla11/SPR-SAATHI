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
        self.action_counts[call_id] = self.action_counts.get(call_id, 0) + 1
        checksum = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        event = {
            "type": "keyboard_type_tool_received",
            "timestamp": time.time(),
            "call_id": call_id,
            "call_count_for_id": self.action_counts[call_id],
            "text_length": len(text),
            "sha256": checksum,
            "text_preview": text[:60] if len(text) > 60 else text
        }
        self.events.append(event)
        return event

    def record_type_text_start(self, call_id: str, text: str, chunk_size: int) -> Dict[str, Any]:
        self.type_text_counts[call_id] = self.type_text_counts.get(call_id, 0) + 1
        checksum = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        event = {
            "type": "type_text_invoked",
            "timestamp": time.time(),
            "call_id": call_id,
            "invocation_count_for_id": self.type_text_counts[call_id],
            "text_length": len(text),
            "chunk_size": chunk_size,
            "sha256": checksum,
            "text_preview": text[:60] if len(text) > 60 else text
        }
        self.events.append(event)
        return event

    def record_chunk_sent(
        self,
        call_id: str,
        chunk_idx: int,
        char_start: int,
        char_end: int,
        chunk_str: str,
        events_generated: int,
        events_sent: int,
        retried: bool = False
    ):
        event = {
            "type": "chunk_sendinput",
            "timestamp": time.time(),
            "call_id": call_id,
            "chunk_idx": chunk_idx,
            "char_range": [char_start, char_end],
            "chunk_str": chunk_str,
            "events_generated": events_generated,
            "events_sent": events_sent,
            "retried": retried
        }
        self.events.append(event)

KEYBOARD_TRACER = KeyboardTraceLogger()
