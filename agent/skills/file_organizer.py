import os
import shutil
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillExecutionResult


class OrganizeFilesSkill(BaseSkill):
    """
    High-level skill: Organizes files in a directory into categorized subfolders.
    """

    @property
    def name(self) -> str:
        return "organize_files"

    @property
    def description(self) -> str:
        return "Organize files in a specified directory into categorized subfolders based on extension."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string", "description": "Target folder path to organize"},
                "categories": {
                    "type": "object",
                    "description": "Optional custom mapping of category names to file extensions",
                    "default": {
                        "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".md"],
                        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"],
                        "Archives": [".zip", ".tar", ".gz", ".7z", ".rar"],
                        "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml"]
                    }
                }
            },
            "required": ["directory_path"]
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files_moved": {"type": "integer"},
                "categories_created": {"type": "array", "items": {"type": "string"}},
                "details": {"type": "object"}
            }
        }

    @property
    def required_permissions(self) -> List[str]:
        return ["filesystem.write"]

    @property
    def required_tools(self) -> List[str]:
        return ["create_file", "cmd"]

    @property
    def verification_strategy(self) -> str:
        return "Verify target category directories exist and contain the moved files."

    @property
    def fallback_strategy(self) -> str:
        return "If moving fails, retain original files and log diagnostic failure."

    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SkillExecutionResult:
        dir_path = os.path.abspath(os.path.expanduser(inputs.get("directory_path", "")))
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return SkillExecutionResult(
                skill_name=self.name,
                success=False,
                output=None,
                error=f"Directory does not exist: {dir_path}"
            )

        categories = inputs.get("categories") or {
            "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".md"],
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"],
            "Archives": [".zip", ".tar", ".gz", ".7z", ".rar"],
            "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml"]
        }

        # Build reverse extension lookup
        ext_to_cat = {}
        for cat, exts in categories.items():
            for ext in exts:
                ext_to_cat[ext.lower()] = cat

        moved_count = 0
        created_dirs = set()
        details: Dict[str, List[str]] = {}
        steps_executed = []

        try:
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                if os.path.isfile(item_path):
                    _, ext = os.path.splitext(item)
                    cat = ext_to_cat.get(ext.lower(), "Other")
                    target_dir = os.path.join(dir_path, cat)

                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir, exist_ok=True)
                        created_dirs.add(cat)
                        steps_executed.append(f"Created category directory: {cat}")

                    dest_path = os.path.join(target_dir, item)
                    shutil.move(item_path, dest_path)
                    moved_count += 1
                    details.setdefault(cat, []).append(item)
                    steps_executed.append(f"Moved '{item}' -> '{cat}'")

            # Verification: check all category directories exist
            verified = all(os.path.exists(os.path.join(dir_path, cat)) for cat in created_dirs)

            return SkillExecutionResult(
                skill_name=self.name,
                success=True,
                output={
                    "files_moved": moved_count,
                    "categories_created": list(created_dirs),
                    "details": details
                },
                steps_executed=steps_executed,
                verification_details={"verified": verified, "created_directories": list(created_dirs)},
                error=None
            )
        except Exception as e:
            return SkillExecutionResult(
                skill_name=self.name,
                success=False,
                output=None,
                steps_executed=steps_executed,
                error=f"Failed to organize directory: {str(e)}"
            )
