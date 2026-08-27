import os
import json
from typing import Dict, Any

DEFAULT_POLICIES: Dict[str, str] = {
    "mouse": "prompt",
    "keyboard": "prompt",
    "applications": "prompt",
    "filesystem": "prompt",
    "browser": "prompt",
    "terminal": "deny",
    "powershell": "deny"
}

CONFIG_DIR = r"C:\Users\Aaryan shukla\.gemini\antigravity-ide"
CONFIG_PATH = os.path.join(CONFIG_DIR, "permissions_config.json")

class PolicyManager:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.policies = DEFAULT_POLICIES.copy()
        self.app_policies: Dict[str, str] = {
            "chrome.exe": "allow",
            "mspaint.exe": "prompt",
            "notepad.exe": "deny"
        }
        self.load_from_file()

    def get_policy(self, tool_name: str, category: str, arguments: Dict[str, Any]) -> str:
        """
        Precedence rules:
        1. Specific Application Rule (if tool is launch_app or focus_window)
        2. Specific Tool/Resource Rule
        3. Global Scope Category Rule
        4. Default Scope Category
        """
        # 1. Check Specific Application Rule
        if tool_name in ["launch_app", "focus_window"]:
            # Extract application executable name
            app_raw = arguments.get("app_name") or arguments.get("process_name") or ""
            if not app_raw and tool_name == "focus_window":
                app_raw = arguments.get("title_substring") or ""
            
            app_name = str(app_raw).lower().strip()
            if app_name:
                # Add .exe suffix if missing to normalize overrides checking
                if not app_name.endswith(".exe") and app_name in ["chrome", "notepad", "mspaint", "paint", "calc", "calculator"]:
                    if app_name == "paint":
                        app_name = "mspaint.exe"
                    elif app_name == "calculator":
                        app_name = "calc.exe"
                    else:
                        app_name = f"{app_name}.exe"
                        
                for key, val in self.app_policies.items():
                    if key.lower().strip() == app_name or key.lower().replace(".exe", "") == app_name.replace(".exe", ""):
                        return val

        # 2. Check Specific Tool Rule
        if tool_name in self.policies:
            return self.policies[tool_name]

        # 3. Check Global Category Scope Rule
        if category in self.policies:
            return self.policies[category]

        # 4. Fallback Default Category
        return DEFAULT_POLICIES.get(category, "prompt")

    def update_policy(self, scope: str, level: str):
        if level in ["allow", "deny", "prompt"]:
            self.policies[scope] = level
            self.save_to_file()

    def update_app_policy(self, app_name: str, level: str):
        if level in ["allow", "deny", "prompt"]:
            self.app_policies[app_name.lower().strip()] = level
            self.save_to_file()

    def delete_app_policy(self, app_name: str):
        self.app_policies.pop(app_name.lower().strip(), None)
        self.save_to_file()

    def get_all_policies(self) -> Dict[str, Any]:
        return {
            "policies": self.policies,
            "app_policies": self.app_policies
        }

    def load_from_file(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    self.policies.update(data.get("policies", {}))
                    self.app_policies = data.get("app_policies", self.app_policies)
            except Exception:
                pass

    def save_to_file(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump({
                    "policies": self.policies,
                    "app_policies": self.app_policies
                }, f, indent=4)
        except Exception:
            pass
