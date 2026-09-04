import os
import re
import time
import hashlib
import mimetypes
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("agent.core.workspace")


class FileType(str, Enum):
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    IMAGE = "image"
    CODE = "code"
    DATA = "data"
    ARCHIVE = "archive"
    TEXT = "text"
    UNKNOWN = "unknown"


class FileOrigin(str, Enum):
    USER_UPLOAD = "user_upload"
    EXISTING = "existing"
    AGENT_GENERATED = "agent_generated"
    MODIFIED = "modified"
    INTERMEDIATE_ARTIFACT = "intermediate_artifact"
    FINAL_DELIVERABLE = "final_deliverable"
    TEMPORARY = "temporary"


@dataclass
class FileMetadata:
    path: str
    filename: str
    extension: str
    size_bytes: int
    created_time: float
    modified_time: float
    file_type: FileType
    file_origin: FileOrigin
    sha256_hash: str
    parent_task_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "created_time": self.created_time,
            "modified_time": self.modified_time,
            "file_type": self.file_type.value if hasattr(self.file_type, "value") else str(self.file_type),
            "file_origin": self.file_origin.value if hasattr(self.file_origin, "value") else str(self.file_origin),
            "sha256_hash": self.sha256_hash,
            "parent_task_id": self.parent_task_id,
            "tags": self.tags
        }


class WorkspaceManager:
    """
    Phase 6: Workspace and File Intelligence System.
    
    Tracks:
    - User uploads
    - Existing files
    - Temporary files
    - Generated files
    - Modified files
    - Intermediate artifacts
    - Final deliverables
    
    Capabilities:
    - Multi-directory intelligent file search
    - Fuzzy matching & relevance scoring
    - File type understanding & metadata extraction
    - SHA256 change tracking & modification history
    """

    EXTENSION_MAP = {
        # Documents
        ".pdf": FileType.DOCUMENT,
        ".docx": FileType.DOCUMENT,
        ".doc": FileType.DOCUMENT,
        ".odt": FileType.DOCUMENT,
        ".rtf": FileType.DOCUMENT,
        # Spreadsheets
        ".xlsx": FileType.SPREADSHEET,
        ".xls": FileType.SPREADSHEET,
        ".csv": FileType.SPREADSHEET,
        ".tsv": FileType.SPREADSHEET,
        # Presentations
        ".pptx": FileType.PRESENTATION,
        ".ppt": FileType.PRESENTATION,
        ".odp": FileType.PRESENTATION,
        # Images
        ".png": FileType.IMAGE,
        ".jpg": FileType.IMAGE,
        ".jpeg": FileType.IMAGE,
        ".gif": FileType.IMAGE,
        ".svg": FileType.IMAGE,
        ".webp": FileType.IMAGE,
        # Code
        ".py": FileType.CODE,
        ".js": FileType.CODE,
        ".ts": FileType.CODE,
        ".html": FileType.CODE,
        ".css": FileType.CODE,
        ".json": FileType.CODE,
        ".yaml": FileType.CODE,
        ".yml": FileType.CODE,
        # Data
        ".xml": FileType.DATA,
        ".sql": FileType.DATA,
        ".sqlite": FileType.DATA,
        ".db": FileType.DATA,
        # Archives
        ".zip": FileType.ARCHIVE,
        ".tar": FileType.ARCHIVE,
        ".gz": FileType.ARCHIVE,
        ".7z": FileType.ARCHIVE,
        ".rar": FileType.ARCHIVE,
        # Text
        ".txt": FileType.TEXT,
        ".md": FileType.TEXT,
        ".log": FileType.TEXT,
    }

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = os.path.abspath(workspace_root or os.getcwd())
        self.tracked_files: Dict[str, FileMetadata] = {}
        self.modification_history: List[Dict[str, Any]] = []

    def detect_file_type(self, path: str) -> FileType:
        """Determines the file type category based on extension and mime type."""
        _, ext = os.path.splitext(path.lower())
        if ext in self.EXTENSION_MAP:
            return self.EXTENSION_MAP[ext]
        
        mime, _ = mimetypes.guess_type(path)
        if mime:
            if mime.startswith("image/"):
                return FileType.IMAGE
            elif mime.startswith("text/"):
                return FileType.TEXT
        return FileType.UNKNOWN

    def compute_sha256(self, path: str) -> str:
        """Computes SHA256 checksum for change tracking."""
        if not os.path.exists(path) or not os.path.isfile(path):
            return ""
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def register_file(
        self,
        path: str,
        origin: FileOrigin = FileOrigin.EXISTING,
        task_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[FileMetadata]:
        """Registers and fingerprints a file in the workspace registry."""
        norm_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(norm_path) or not os.path.isfile(norm_path):
            return None

        stat = os.stat(norm_path)
        meta = FileMetadata(
            path=norm_path,
            filename=os.path.basename(norm_path),
            extension=os.path.splitext(norm_path)[1].lower(),
            size_bytes=stat.st_size,
            created_time=stat.st_ctime,
            modified_time=stat.st_mtime,
            file_type=self.detect_file_type(norm_path),
            file_origin=origin,
            sha256_hash=self.compute_sha256(norm_path),
            parent_task_id=task_id,
            tags=tags or []
        )
        self.tracked_files[norm_path] = meta
        return meta

    def track_file_modification(self, path: str, modifier: str = "agent") -> bool:
        """Checks if a file's hash changed and logs the modification event."""
        norm_path = os.path.abspath(os.path.expanduser(path))
        if norm_path not in self.tracked_files:
            self.register_file(norm_path, origin=FileOrigin.MODIFIED)
            return True

        old_meta = self.tracked_files[norm_path]
        new_hash = self.compute_sha256(norm_path)
        if new_hash != old_meta.sha256_hash:
            stat = os.stat(norm_path)
            self.modification_history.append({
                "path": norm_path,
                "old_hash": old_meta.sha256_hash,
                "new_hash": new_hash,
                "timestamp": time.time(),
                "modifier": modifier
            })
            old_meta.sha256_hash = new_hash
            old_meta.size_bytes = stat.st_size
            old_meta.modified_time = stat.st_mtime
            if old_meta.file_origin != FileOrigin.AGENT_GENERATED:
                old_meta.file_origin = FileOrigin.MODIFIED
            return True
        return False

    def search_files(
        self,
        query: str,
        file_types: Optional[List[FileType]] = None,
        search_dirs: Optional[List[str]] = None,
        max_results: int = 15
    ) -> List[Tuple[FileMetadata, float]]:
        """
        Intelligently searches files across workspace and system locations.
        Ranks results using relevance scoring (exact match, token overlap, recency).
        """
        results: List[Tuple[FileMetadata, float]] = []
        q_tokens = set(re.findall(r"\w+", query.lower())) if query else set()

        scan_dirs = search_dirs or [self.workspace_root]
        scanned_paths: Set[str] = set()

        for d in scan_dirs:
            if not os.path.exists(d):
                continue
            for root, dirs, files in os.walk(d):
                # Ignore noise folders
                dirs[:] = [d_name for d_name in dirs if d_name not in [".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"]]
                for f in files:
                    full_p = os.path.join(root, f)
                    scanned_paths.add(full_p)
                    if full_p not in self.tracked_files:
                        self.register_file(full_p, origin=FileOrigin.EXISTING)

        for meta in self.tracked_files.values():
            # Filter by file_types if specified
            if file_types and meta.file_type not in file_types:
                continue

            score = 0.0
            name_lower = meta.filename.lower()
            name_tokens = set(re.findall(r"\w+", name_lower))

            if query:
                # Exact name match
                if query.lower() == name_lower:
                    score += 10.0
                elif query.lower() in name_lower:
                    score += 5.0

                # Token overlap
                overlap = len(q_tokens & name_tokens)
                score += overlap * 2.0
            else:
                score = 1.0

            # Recency boost (files modified within the last 7 days receive higher rank)
            age_days = (time.time() - meta.modified_time) / 86400.0
            if age_days < 1:
                score += 3.0
            elif age_days < 7:
                score += 1.5

            if score > 0:
                results.append((meta, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_results]

    def get_files_by_origin(self, origin: FileOrigin, task_id: Optional[str] = None) -> List[FileMetadata]:
        """Returns files filtered by their lifecycle origin and optional task ID."""
        files = [m for m in self.tracked_files.values() if m.file_origin == origin]
        if task_id:
            files = [m for m in files if m.parent_task_id == task_id]
        return files


# Global singleton instance
WORKSPACE_MANAGER = WorkspaceManager()
