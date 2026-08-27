from typing import Dict, Any
from .base import BaseTool

class OpenBrowserUrlTool(BaseTool):
    @property
    def name(self) -> str:
        return "open_browser_url"

    @property
    def description(self) -> str:
        return "Open a web browser pointing to a specific URL."

    @property
    def category(self) -> str:
        return "browser"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to on startup"}
            },
            "required": ["url"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        url = arguments.get("url", "")
        # Since this is phase 0, print log message 
        msg = f"Opening browser and navigating to URL: {url}"
        print(msg)
        return {
            "call_id": "",
            "success": True,
            "output": msg,
            "error": None
        }
