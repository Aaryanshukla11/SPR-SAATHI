import os
import csv
import json
from typing import Dict, Any, List, Optional
from .base import BaseSkill, SkillExecutionResult


class AnalyzeDatasetSkill(BaseSkill):
    """
    High-level skill: Analyzes tabular CSV or JSON datasets and produces statistical summaries.
    """

    @property
    def name(self) -> str:
        return "analyze_dataset"

    @property
    def description(self) -> str:
        return "Analyze a CSV or JSON dataset and calculate summary metrics, column types, row counts, and numeric statistics."

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to CSV or JSON data file"}
            },
            "required": ["file_path"]
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "row_count": {"type": "integer"},
                "column_count": {"type": "integer"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "object"}
            }
        }

    @property
    def required_permissions(self) -> List[str]:
        return ["filesystem.read"]

    @property
    def required_tools(self) -> List[str]:
        return ["read_file"]

    @property
    def verification_strategy(self) -> str:
        return "Verify dataset parsed successfully with row count >= 0 and non-empty schema."

    @property
    def fallback_strategy(self) -> str:
        return "Attempt reading raw text lines if structured delimiter parsing fails."

    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SkillExecutionResult:
        file_path = os.path.abspath(os.path.expanduser(inputs.get("file_path", "")))
        if not os.path.exists(file_path):
            return SkillExecutionResult(
                skill_name=self.name,
                success=False,
                output=None,
                error=f"Dataset file not found: {file_path}"
            )

        steps_executed = []
        try:
            _, ext = os.path.splitext(file_path)
            rows: List[Dict[str, Any]] = []
            columns: List[str] = []

            if ext.lower() == ".csv":
                steps_executed.append("Detected CSV format, parsing with csv.DictReader")
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    reader = csv.DictReader(f)
                    columns = reader.fieldnames or []
                    rows = list(reader)
            elif ext.lower() == ".json":
                steps_executed.append("Detected JSON format, parsing with json.load")
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        rows = data
                        columns = list(data[0].keys())
                    elif isinstance(data, dict):
                        rows = [data]
                        columns = list(data.keys())
            else:
                return SkillExecutionResult(
                    skill_name=self.name,
                    success=False,
                    output=None,
                    error=f"Unsupported dataset extension '{ext}'. Must be .csv or .json"
                )

            steps_executed.append(f"Loaded {len(rows)} records with {len(columns)} columns")

            # Calculate numeric column summaries
            summary: Dict[str, Any] = {}
            for col in columns:
                vals = []
                for r in rows:
                    raw_v = r.get(col)
                    if raw_v is not None and raw_v != "":
                        try:
                            vals.append(float(raw_v))
                        except (ValueError, TypeError):
                            pass
                if vals:
                    summary[col] = {
                        "type": "numeric",
                        "count": len(vals),
                        "min": min(vals),
                        "max": max(vals),
                        "mean": round(sum(vals) / len(vals), 2)
                    }
                else:
                    summary[col] = {
                        "type": "text/categorical",
                        "count": len(rows)
                    }

            return SkillExecutionResult(
                skill_name=self.name,
                success=True,
                output={
                    "row_count": len(rows),
                    "column_count": len(columns),
                    "columns": columns,
                    "summary": summary
                },
                steps_executed=steps_executed,
                verification_details={"parsed": True, "rows": len(rows), "columns": len(columns)},
                error=None
            )
        except Exception as e:
            return SkillExecutionResult(
                skill_name=self.name,
                success=False,
                output=None,
                steps_executed=steps_executed,
                error=f"Dataset analysis failed: {str(e)}"
            )
