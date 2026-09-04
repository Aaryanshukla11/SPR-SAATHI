import os
import datetime
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillExecutionResult


class CreateDocumentSkill(BaseSkill):
    """
    High-level skill: Generates structured documents/reports from data or prompts.
    """

    @property
    def name(self) -> str:
        return "create_document"

    @property
    def description(self) -> str:
        return "Create a structured markdown or text report document with formatted headings, tables, and metadata."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Destination file path"},
                "title": {"type": "string", "description": "Document title"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["heading", "content"]
                    },
                    "description": "List of document sections with heading and content"
                },
                "author": {"type": "string", "default": "SPR SAATHI AI", "description": "Document author"}
            },
            "required": ["file_path", "title", "sections"]
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "size_bytes": {"type": "integer"},
                "sections_written": {"type": "integer"}
            }
        }

    @property
    def required_permissions(self) -> List[str]:
        return ["filesystem.write"]

    @property
    def required_tools(self) -> List[str]:
        return ["create_file", "write_file"]

    @property
    def verification_strategy(self) -> str:
        return "Verify target file exists, has size > 0, and contains the document title."

    @property
    def fallback_strategy(self) -> str:
        return "If writing fails, attempt saving to temporary scratch directory and inform user."

    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SkillExecutionResult:
        file_path = os.path.abspath(os.path.expanduser(inputs.get("file_path", "")))
        title = inputs.get("title", "Untitled Document")
        sections = inputs.get("sections", [])
        author = inputs.get("author", "SPR SAATHI AI")
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        steps_executed = []
        try:
            # Format document
            lines = [
                f"# {title}",
                "",
                f"**Author:** {author}  ",
                f"**Generated:** {now_str}",
                "",
                "---",
                ""
            ]

            for s in sections:
                h = s.get("heading", "Section")
                c = s.get("content", "")
                lines.append(f"## {h}")
                lines.append("")
                lines.append(c)
                lines.append("")
                steps_executed.append(f"Formatted section: '{h}'")

            content = "\n".join(lines)

            # Ensure parent directory exists
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
                steps_executed.append(f"Created parent directory: '{parent_dir}'")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            steps_executed.append(f"Written {len(content)} chars to '{file_path}'")

            # Verification
            file_exists = os.path.exists(file_path)
            file_size = os.path.getsize(file_path) if file_exists else 0
            title_verified = False
            if file_exists:
                with open(file_path, "r", encoding="utf-8") as f:
                    title_verified = title in f.read()

            verified = file_exists and file_size > 0 and title_verified

            return SkillExecutionResult(
                skill_name=self.name,
                success=verified,
                output={
                    "file_path": file_path,
                    "size_bytes": file_size,
                    "sections_written": len(sections)
                },
                steps_executed=steps_executed,
                verification_details={
                    "file_exists": file_exists,
                    "size_bytes": file_size,
                    "title_verified": title_verified
                },
                error=None if verified else "Verification failed: File was not created properly."
            )
        except Exception as e:
            return SkillExecutionResult(
                skill_name=self.name,
                success=False,
                output=None,
                steps_executed=steps_executed,
                error=f"Failed to create document: {str(e)}"
            )
