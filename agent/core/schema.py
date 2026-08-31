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

def get_compact_tools_schema() -> str:
    """
    Returns a compact string representation of the registered tools and parameters,
    reducing token count and prompt prefill latency.
    """
    tools = get_all_tools()
    compact_list = []
    for name, tool in tools.items():
        params = []
        props = tool.parameters.get("properties", {})
        req = tool.parameters.get("required", [])
        for p_name, p_info in props.items():
            p_type = p_info.get("type", "string")
            p_desc = p_info.get("description", "")
            req_flag = " (required)" if p_name in req else ""
            params.append(f"{p_name} ({p_type}): {p_desc}{req_flag}")
        params_str = ", ".join(params)
        compact_list.append(f"- {tool.name}: {tool.description}\n  Parameters: {params_str}")
    return "\n".join(compact_list)
