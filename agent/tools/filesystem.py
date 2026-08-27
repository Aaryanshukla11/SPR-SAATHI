import os
from typing import Dict, Any
from .base import BaseTool

class CreateFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "create_file"

    @property
    def description(self) -> str:
        return "Create a new file at the specified path with the given content."

    @property
    def category(self) -> str:
        return "filesystem"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Absolute or relative path to the file"},
                "content": {"type": "string", "description": "Content to write into the file", "default": ""}
            },
            "required": ["filepath"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        filepath = arguments.get("filepath", "")
        content = arguments.get("content", "")
        # For Phase 0, we can write the file safely or log it. Let's log it to avoid actual modifications 
        # unless permissions are set. Actually, let's execute it safely.
        try:
            # Check directory
            dir_name = os.path.dirname(filepath)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            msg = f"Successfully created file at: {filepath}"
            return {
                "call_id": "",
                "success": True,
                "output": msg,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to create file: {str(e)}"
            }


class ReadFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read and return contents of a file at the specified path."

    @property
    def category(self) -> str:
        return "filesystem"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file to read"}
            },
            "required": ["filepath"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        filepath = arguments.get("filepath", "")
        try:
            if not os.path.exists(filepath):
                return {
                    "call_id": "",
                    "success": False,
                    "output": "",
                    "error": f"File does not exist: {filepath}"
                }
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "call_id": "",
                "success": True,
                "output": content,
                "error": None
            }
        except Exception as e:
            return {
                "call_id": "",
                "success": False,
                "output": "",
                "error": f"Failed to read file: {str(e)}"
            }
