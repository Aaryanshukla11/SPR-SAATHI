from typing import List, Dict, Any
from agent.tools import get_all_tools

def get_tools_schema() -> List[Dict[str, Any]]:
    """
    Returns the list of all registered tool schemas.
    Each schema includes name, description, and parameter specifications.
    """
    tools = get_all_tools()
    schemas = []
    for name, tool in tools.items():
        schemas.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters
        })
    return schemas
