import asyncio
import sys
import uvicorn
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import agent components
from agent.core.state import StateTracker
from agent.core.planner import RuleBasedPlanner
from agent.core.executor import ToolExecutor
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.control.takeover import TakeoverManager
from agent.models.local import LocalModelProvider
from agent.models.api import ApiModelProvider

# Initialize core modules
state_tracker = StateTracker()
policy_manager = PolicyManager()
permission_broker = PermissionBroker(policy_manager, state_tracker)
takeover_manager = TakeoverManager()

# Default to API model (Gemini)
current_model_provider = ApiModelProvider(model_name="Gemini 3.5 Flash")
planner = RuleBasedPlanner(current_model_provider)
tools = get_all_tools()
executor = ToolExecutor(tools, permission_broker, takeover_manager)

from contextlib import asynccontextmanager

async def monitor_and_dock_appbar():
    from agent.core.appbar import register_appbar
    # Wait for the Electron window to load and register the appbar
    for _ in range(60): # try for 30 seconds
        try:
            if register_appbar("SPR SAATHI", side='right', width_ratio=0.25):
                print("[AppBar] Registered successfully", flush=True)
                break
        except Exception as e:
            print(f"[AppBar] Register failed: {e}", flush=True)
        await asyncio.sleep(0.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start loop search task
    appbar_task = asyncio.create_task(monitor_and_dock_appbar())
    yield
    # Shutdown: cancel task and unregister appbar
    appbar_task.cancel()
    try:
        from agent.core.appbar import unregister_appbar
        unregister_appbar()
    except Exception:
        pass

# We will instantiate the AgentLoop when the server starts
agent_loop: Optional[AgentLoop] = None

app = FastAPI(title="SPR SAATHI Backend", lifespan=lifespan)

# Allow CORS for Electron UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections
active_connections: List[WebSocket] = []

async def broadcast_event(event: Dict[str, Any]):
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(event)
        except Exception:
            disconnected.append(connection)
    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)

# Register broker callback to prompt via WS
async def on_permission_prompt(request_id: str, tool_name: str, arguments: Dict[str, Any]):
    # Extract user-friendly prompt reasons
    action_desc = f"Use tool '{tool_name}'"
    reason_desc = "Required to complete your requested task."
    
    await broadcast_event({
        "event_type": "permission_required",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": f"Tool '{tool_name}' requires permission to run.",
        "payload": {
            "request_id": request_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "scope": tool_name,
            "resource": tool_name,
            "action": action_desc,
            "reason": reason_desc
        }
    })

permission_broker.on_prompt_callback = on_permission_prompt

# Instantiate loop
agent_loop = AgentLoop(
    state_tracker=state_tracker,
    planner=planner,
    executor=executor,
    takeover_manager=takeover_manager,
    broadcast_callback=broadcast_event
)

# Pydantic Schemas matching the shared contracts
import datetime
class StartTaskRequest(BaseModel):
    task: str

class PermissionResponse(BaseModel):
    request_id: str
    decision: str  # "allow" | "deny"

class ModelConfigRequest(BaseModel):
    provider: str  # "local" | "api"
    model_name: str
    api_key: Optional[str] = None

class PolicyConfigRequest(BaseModel):
    scope: str
    level: str  # "allow" | "deny" | "prompt"

class ScopeUpdate(BaseModel):
    level: str  # "allow" | "deny" | "prompt"

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/state")
async def get_state():
    return state_tracker.to_dict()

@app.post("/api/task/start")
async def start_task(req: StartTaskRequest):
    if state_tracker.status not in ["idle", "stopped", "completed", "error", "failed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Agent is already busy running a task.")
    
    agent_loop.start_task(req.task)
    return {"status": "started", "task_id": state_tracker.task_id}

@app.post("/api/task/stop")
async def stop_task():
    agent_loop.stop_task()
    return {"status": "stopped"}

@app.get("/api/control/state")
async def get_control_state():
    return {"control_state": takeover_manager.control_state}

@app.post("/api/control/takeover")
@app.post("/api/takeover/take")
async def take_control_endpoint():
    success = takeover_manager.take_control()
    if not success:
        raise HTTPException(status_code=400, detail="Invalid state transition: cannot take control in current state.")
    
    agent_loop.pause_task_for_takeover()
    state_tracker.takeover_active = True
    
    await broadcast_event({
        "event_type": "control.takeover_started",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": "User took control. AI execution paused.",
        "payload": {
            "takeover_active": True,
            "control_state": takeover_manager.control_state
        }
    })
    return {"status": "paused_by_user", "control_state": takeover_manager.control_state}

@app.post("/api/control/release")
@app.post("/api/takeover/release")
async def release_control_endpoint():
    # If the task was stopped/cancelled while user had control, reject release resume
    if state_tracker.status in ["cancelled", "stopped", "completed", "failed"]:
        # Just update takeover manager control state back to AI_CONTROL without loop resume
        takeover_manager.release_control()
        state_tracker.takeover_active = False
        return {"status": "released_no_resume", "control_state": takeover_manager.control_state}

    success = takeover_manager.release_control()
    if not success:
        raise HTTPException(status_code=400, detail="Invalid state transition: cannot release control in current state.")
    
    state_tracker.takeover_active = False
    await broadcast_event({
        "event_type": "control.release_requested",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": "User released control. Resuming AI execution...",
        "payload": {
            "takeover_active": False,
            "control_state": takeover_manager.control_state
        }
    })
    
    asyncio.create_task(agent_loop.resume_task_after_takeover())
    return {"status": "resumed", "control_state": takeover_manager.control_state}

# Permissions REST endpoints matching Requirement 18
@app.get("/api/permissions")
async def get_all_permissions_api():
    return policy_manager.get_all_policies()

@app.put("/api/permissions/{scope}")
async def update_scope_permission_api(scope: str, req: ScopeUpdate):
    lvl = req.level.lower().strip()
    if lvl not in ["allow", "deny", "prompt"]:
        raise HTTPException(status_code=400, detail="Invalid policy level. Choose 'allow', 'deny', or 'prompt'")
    policy_manager.update_policy(scope, lvl)
    # Broadcast configuration update to the UI
    await broadcast_event({
        "event_type": "permission.updated",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": f"Global policy for scope '{scope}' updated to '{lvl}'.",
        "payload": {"policies": policy_manager.get_all_policies()}
    })
    return {"status": "policy_updated", "scope": scope, "level": lvl}

@app.get("/api/config/installed_apps")
async def get_installed_apps_endpoint():
    from agent.core.win32_utils import get_installed_applications
    return get_installed_applications()

@app.put("/api/permissions/application/{app_id}")
async def update_app_permission_api(app_id: str, req: ScopeUpdate):
    lvl = req.level.lower().strip()
    if lvl not in ["allow", "deny", "prompt"]:
        raise HTTPException(status_code=400, detail="Invalid policy level. Choose 'allow', 'deny', or 'prompt'")
    policy_manager.update_app_policy(app_id, lvl)
    await broadcast_event({
        "event_type": "permission.updated",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": f"App override policy for '{app_id}' updated to '{lvl}'.",
        "payload": {"policies": policy_manager.get_all_policies()}
    })
    return {"status": "app_policy_updated", "app_id": app_id, "level": lvl}

@app.delete("/api/permissions/application/{app_id}")
async def delete_app_permission_api(app_id: str):
    policy_manager.delete_app_policy(app_id)
    await broadcast_event({
        "event_type": "permission.updated",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": f"App override policy for '{app_id}' deleted.",
        "payload": {"policies": policy_manager.get_all_policies()}
    })
    return {"status": "app_policy_deleted", "app_id": app_id}

@app.post("/api/permissions/request/{request_id}/decision")
async def respond_permission_api(request_id: str, req: ScopeUpdate):
    decision = req.level.lower().strip()
    if decision not in ["allow", "deny"]:
        raise HTTPException(status_code=400, detail="Decision must be 'allow' or 'deny'")
    success = permission_broker.resolve_permission(request_id, decision)
    if not success:
        raise HTTPException(status_code=404, detail="Permission request ID not found or already resolved.")
    return {"status": "resolved"}

@app.get("/api/permissions/audit")
async def get_audit_trail_api():
    return permission_broker.audit_trail

@app.post("/api/permission/respond")
async def respond_permission(req: PermissionResponse):
    success = permission_broker.resolve_permission(req.request_id, req.decision)
    if not success:
        raise HTTPException(status_code=404, detail="Permission request ID not found or already resolved.")
    return {"status": "resolved"}

@app.post("/api/config/model")
async def configure_model(req: ModelConfigRequest):
    global current_model_provider, planner, agent_loop
    
    config = {}
    if req.api_key:
        config["api_key"] = req.api_key
        import os
        name = req.model_name.lower()
        if "gpt" in name or "openai" in name:
            os.environ["OPENAI_API_KEY"] = req.api_key
        elif "gemini" in name:
            os.environ["GEMINI_API_KEY"] = req.api_key
            os.environ["GOOGLE_API_KEY"] = req.api_key
        elif "claude" in name or "anthropic" in name or "sonnet" in name or "haiku" in name:
            os.environ["ANTHROPIC_API_KEY"] = req.api_key
            
    if req.provider.lower() == "local":
        current_model_provider = LocalModelProvider(model_name=req.model_name, config=config)
    elif req.provider.lower() in ["api", "gemini", "openai", "anthropic"]:
        current_model_provider = ApiModelProvider(model_name=req.model_name, config=config)
    else:
        raise HTTPException(status_code=400, detail="Invalid provider. Choose 'local' or 'api'")
    
    planner = RuleBasedPlanner(current_model_provider)
    agent_loop.planner = planner
    
    return {"status": "model_updated", "provider": req.provider, "model_name": req.model_name}

@app.get("/api/config/ollama_models")
async def get_ollama_models():
    import urllib.request
    import json
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as response:
            data = json.loads(response.read().decode())
            return {"status": "success", "models": [m.get("name", "") for m in data.get("models", [])]}
    except Exception as e:
        return {"status": "error", "message": str(e), "models": []}

@app.get("/api/config/keys")
async def get_configured_keys():
    import os
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY"))
    }

@app.get("/api/config/permission")
async def get_permissions():
    return policy_manager.get_all_policies()

class UserQuestionResponse(BaseModel):
    response: str

@app.post("/api/task/respond_question")
async def respond_user_question(req: UserQuestionResponse):
    if agent_loop and agent_loop._user_response_future and not agent_loop._user_response_future.done():
        agent_loop._user_response_future.set_result(req.response)
        return {"status": "resolved"}
    raise HTTPException(status_code=400, detail="No active user prompt question found.")

@app.post("/api/task/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"
        
        provider = current_model_provider
        # Fallback to ApiModelProvider if local model is active but API key env vars are present
        if hasattr(provider, "model_name") and "local" in getattr(provider, "model_name", "").lower():
            import os
            if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("OPENAI_API_KEY"):
                provider = ApiModelProvider(model_name="Gemini 3.5 Flash")
                
        transcription = await provider.transcribe_audio(audio_bytes, mime_type)
        return {"status": "success", "transcription": transcription}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Send initial state to newly connected client
        await websocket.send_json({
            "event_type": "status_change",
            "timestamp": "",
            "task_id": state_tracker.task_id,
            "message": "WebSocket connection established.",
            "payload": {"state": state_tracker.to_dict(), "policies": policy_manager.get_all_policies()}
        })
        while True:
            # We don't expect messages from client via WS, keep alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception:
        if websocket in active_connections:
            active_connections.remove(websocket)


# Custom Uvicorn Server class to print bound port and handle clean startup/shutdown
class CustomUvicornServer(uvicorn.Server):
    def install_signal_handlers(self):
        # We handle lifecycle from Electron, let's bypass custom signal handling that blocks on Windows
        pass

    async def startup(self, sockets=None):
        await super().startup(sockets=sockets)
        
        # Extract actual bound port
        bound_port = None
        for server in self.servers:
            for socket in server.sockets:
                bound_port = socket.getsockname()[1]
                break
        
        if bound_port:
            print(f"PORT: {bound_port}", flush=True)
        else:
            print("PORT: FAILED", flush=True)

async def start_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = CustomUvicornServer(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        pass
