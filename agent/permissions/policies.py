from typing import Dict

# Permission states: "allow", "deny", "prompt"
DEFAULT_POLICIES: Dict[str, str] = {
    "computer": "prompt",     # mouse/keyboard
    "windows": "allow",       # app launching
    "filesystem": "prompt",   # file CRUD
    "terminal": "prompt",     # CMD / PowerShell
    "browser": "allow"        # URL opening
}

class PolicyManager:
    def __init__(self):
        self.policies = DEFAULT_POLICIES.copy()

    def get_policy(self, tool_name: str, category: str) -> str:
        # Check specific tool policy first
        if tool_name in self.policies:
            return self.policies[tool_name]
        # Fall back to category policy
        if category in self.policies:
            return self.policies[category]
        # Global fallback
        return self.policies.get("global", "prompt")

    def update_policy(self, scope: str, level: str):
        if level in ["allow", "deny", "prompt"]:
            self.policies[scope] = level

    def get_all_policies(self) -> Dict[str, str]:
        return self.policies
