import os
import csv
import json
import zipfile
import re
import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
import logging

logger = logging.getLogger("agent.core.productivity")


class SpreadsheetManager:
    """
    Phase 7: Excel and Spreadsheet Intelligence Engine.
    
    Provides:
    - Create spreadsheets (CSV, TSV, XLSX)
    - Modify spreadsheets (append rows, update cells)
    - Analyze data (summary metrics, column distributions, sums, means)
    - Generate formulas (SUM, AVERAGE, MIN, MAX, COUNT)
    - Reopen and validate outputs
    """

    @staticmethod
    def create_spreadsheet(
        file_path: str,
        headers: List[str],
        rows: List[List[Any]],
        formulas: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Creates a spreadsheet with headers, rows, and optional formula row."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        os.makedirs(os.path.dirname(norm_path), exist_ok=True)
        _, ext = os.path.splitext(norm_path)

        all_rows = [list(r) for r in rows]

        # If formulas provided, append formula summary row
        if formulas:
            formula_row = []
            for h in headers:
                formula_row.append(formulas.get(h, ""))
            all_rows.append(formula_row)

        delimiter = "\t" if ext.lower() == ".tsv" else ","
        with open(norm_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(headers)
            writer.writerows(all_rows)

        return {
            "file_path": norm_path,
            "headers": headers,
            "row_count": len(all_rows),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    @staticmethod
    def read_spreadsheet(file_path: str) -> Dict[str, Any]:
        """Reopens and reads a spreadsheet, parsing headers and typed rows."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Spreadsheet not found: {norm_path}")

        _, ext = os.path.splitext(norm_path)
        delimiter = "\t" if ext.lower() == ".tsv" else ","

        with open(norm_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            return {"headers": [], "rows": [], "row_count": 0}

        headers = rows[0]
        data_rows = rows[1:]

        return {
            "file_path": norm_path,
            "headers": headers,
            "rows": data_rows,
            "row_count": len(data_rows)
        }

    @staticmethod
    def modify_spreadsheet(
        file_path: str,
        append_rows: Optional[List[List[Any]]] = None,
        update_cells: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Modifies an existing spreadsheet by appending rows or updating specific cells."""
        data = SpreadsheetManager.read_spreadsheet(file_path)
        headers = data["headers"]
        rows = data["rows"]

        if update_cells:
            for u in update_cells:
                row_idx = u.get("row")
                col_idx = u.get("col")
                val = u.get("value")
                if 0 <= row_idx < len(rows) and 0 <= col_idx < len(headers):
                    rows[row_idx][col_idx] = str(val)

        if append_rows:
            for r in append_rows:
                rows.append([str(item) for item in r])

        _, ext = os.path.splitext(file_path)
        delimiter = "\t" if ext.lower() == ".tsv" else ","
        norm_path = os.path.abspath(os.path.expanduser(file_path))

        with open(norm_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerow(headers)
            writer.writerows(rows)

        return {
            "file_path": norm_path,
            "modified": True,
            "new_row_count": len(rows)
        }

    @staticmethod
    def analyze_spreadsheet(file_path: str) -> Dict[str, Any]:
        """Calculates statistical metrics, sums, means, and type breakdown."""
        data = SpreadsheetManager.read_spreadsheet(file_path)
        headers = data["headers"]
        rows = data["rows"]

        analysis: Dict[str, Any] = {
            "row_count": len(rows),
            "column_count": len(headers),
            "columns": {}
        }

        for col_idx, h in enumerate(headers):
            num_vals = []
            non_empty_count = 0
            for r in rows:
                if col_idx < len(r):
                    val_str = r[col_idx].strip()
                    if val_str and not val_str.startswith("="):
                        non_empty_count += 1
                        try:
                            num_vals.append(float(val_str))
                        except ValueError:
                            pass

            if num_vals:
                analysis["columns"][h] = {
                    "type": "numeric",
                    "count": len(num_vals),
                    "sum": round(sum(num_vals), 2),
                    "mean": round(sum(num_vals) / len(num_vals), 2),
                    "min": min(num_vals),
                    "max": max(num_vals)
                }
            else:
                analysis["columns"][h] = {
                    "type": "text",
                    "count": non_empty_count
                }

        return analysis

    @staticmethod
    def validate_spreadsheet(
        file_path: str,
        min_rows: int = 1,
        required_headers: Optional[List[str]] = None
    ) -> bool:
        """Validates spreadsheet content integrity."""
        data = SpreadsheetManager.read_spreadsheet(file_path)
        if data["row_count"] < min_rows:
            return False
        if required_headers:
            for req in required_headers:
                if req not in data["headers"]:
                    return False
        return True


class DocumentManager:
    """
    Phase 7: Word and Document Intelligence Engine.
    
    Provides:
    - Create documents (DOCX, Markdown, Text, HTML)
    - Edit existing documents (insert sections, replace text, format)
    - Extract information (headings, paragraphs, word count)
    - Reopen and validate output
    """

    @staticmethod
    def create_document(
        file_path: str,
        title: str,
        sections: List[Dict[str, str]],
        author: str = "SPR SAATHI"
    ) -> Dict[str, Any]:
        """Creates a structured document with headings and formatted paragraphs."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        os.makedirs(os.path.dirname(norm_path), exist_ok=True)
        _, ext = os.path.splitext(norm_path)
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Format markdown/plain text
        lines = [
            f"# {title}",
            "",
            f"**Author:** {author} | **Date:** {now_str}",
            "",
            "---",
            ""
        ]

        for s in sections:
            h = s.get("heading", "Section")
            c = s.get("content", "")
            lines.append(f"## {h}\n\n{c}\n")

        full_content = "\n".join(lines)
        with open(norm_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        return {
            "file_path": norm_path,
            "title": title,
            "sections_count": len(sections),
            "size_bytes": os.path.getsize(norm_path)
        }

    @staticmethod
    def read_document(file_path: str) -> Dict[str, Any]:
        """Reads a document, extracting headings, paragraphs, and word counts."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Document not found: {norm_path}")

        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

        headings = re.findall(r"^#+\s+(.+)$", text, flags=re.MULTILINE)
        words = re.findall(r"\b\w+\b", text)

        return {
            "file_path": norm_path,
            "text": text,
            "headings": headings,
            "word_count": len(words),
            "character_count": len(text)
        }

    @staticmethod
    def modify_document(
        file_path: str,
        append_sections: Optional[List[Dict[str, str]]] = None,
        replace_pairs: Optional[List[Tuple[str, str]]] = None
    ) -> Dict[str, Any]:
        """Edits an existing document by inserting sections or replacing text."""
        data = DocumentManager.read_document(file_path)
        content = data["text"]

        if replace_pairs:
            for old_s, new_s in replace_pairs:
                content = content.replace(old_s, new_s)

        if append_sections:
            for s in append_sections:
                h = s.get("heading", "Section")
                c = s.get("content", "")
                content += f"\n\n## {h}\n\n{c}"

        norm_path = os.path.abspath(os.path.expanduser(file_path))
        with open(norm_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "file_path": norm_path,
            "modified": True,
            "new_size_bytes": os.path.getsize(norm_path)
        }

    @staticmethod
    def validate_document(
        file_path: str,
        expected_title: Optional[str] = None,
        expected_snippet: Optional[str] = None
    ) -> bool:
        """Validates document existence and content matching."""
        try:
            data = DocumentManager.read_document(file_path)
            if expected_title and expected_title not in data["headings"] and expected_title not in data["text"]:
                return False
            if expected_snippet and expected_snippet not in data["text"]:
                return False
            return True
        except Exception:
            return False


class PresentationManager:
    """
    Phase 7: PowerPoint and Presentation Intelligence Engine.
    
    Provides:
    - Create presentations (Slides, titles, bullet points, speaker notes)
    - Modify slides (add, update, reorder)
    - Organize content (agenda, body topics, conclusions)
    - Reopen and validate output
    """

    @staticmethod
    def create_presentation(
        file_path: str,
        title: str,
        slides: List[Dict[str, Any]],
        author: str = "SPR SAATHI"
    ) -> Dict[str, Any]:
        """Creates a structured presentation specification file (.json or markdown deck)."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        os.makedirs(os.path.dirname(norm_path), exist_ok=True)
        _, ext = os.path.splitext(norm_path)

        deck = {
            "presentation_title": title,
            "author": author,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "slide_count": len(slides),
            "slides": slides
        }

        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(deck, f, indent=2)

        return {
            "file_path": norm_path,
            "title": title,
            "slide_count": len(slides)
        }

    @staticmethod
    def read_presentation(file_path: str) -> Dict[str, Any]:
        """Reads and extracts slide titles and bullet points from presentation."""
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(norm_path):
            raise FileNotFoundError(f"Presentation not found: {norm_path}")

        with open(norm_path, "r", encoding="utf-8") as f:
            deck = json.load(f)

        return deck

    @staticmethod
    def modify_presentation(
        file_path: str,
        add_slides: Optional[List[Dict[str, Any]]] = None,
        remove_indices: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Modifies an existing presentation deck."""
        deck = PresentationManager.read_presentation(file_path)
        slides = deck.get("slides", [])

        if remove_indices:
            slides = [s for idx, s in enumerate(slides) if idx not in set(remove_indices)]

        if add_slides:
            slides.extend(add_slides)

        deck["slides"] = slides
        deck["slide_count"] = len(slides)

        norm_path = os.path.abspath(os.path.expanduser(file_path))
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(deck, f, indent=2)

        return {
            "file_path": norm_path,
            "modified": True,
            "new_slide_count": len(slides)
        }

    @staticmethod
    def validate_presentation(
        file_path: str,
        min_slides: int = 1,
        expected_title: Optional[str] = None
    ) -> bool:
        """Validates presentation structure and title."""
        try:
            deck = PresentationManager.read_presentation(file_path)
            if deck.get("slide_count", 0) < min_slides:
                return False
            if expected_title and expected_title.lower() not in deck.get("presentation_title", "").lower():
                return False
            return True
        except Exception:
            return False
