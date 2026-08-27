import asyncio
import sys
import uvicorn
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
executor = ToolExecutor(tools, permission_broker)

# We will instantiate the AgentLoop when the server starts
agent_loop: Optional[AgentLoop] = None

app = FastAPI(title="SPR SAATHI Backend")

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

class PolicyConfigRequest(BaseModel):
    scope: str
    level: str  # "allow" | "deny" | "prompt"

class ScopeUpdate(BaseModel):
    level: str  # "allow" | "deny" | "prompt"

@app.get("/api/state")
async def get_state():
    return state_tracker.to_dict()

@app.post("/api/task/start")
async def start_task(req: StartTaskRequest):
    if state_tracker.status not in ["idle", "stopped", "completed", "error"]:
        raise HTTPException(status_code=400, detail="Agent is already busy running a task.")
    
    agent_loop.start_task(req.task)
    return {"status": "started", "task_id": state_tracker.task_id}

@app.post("/api/task/stop")
async def stop_task():
    agent_loop.stop_task()
    return {"status": "stopped"}

@app.post("/api/takeover/take")
async def take_control():
    takeover_manager.take_control()
    state_tracker.takeover_active = True
    await broadcast_event({
        "event_type": "takeover",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": "User took control. AI execution paused.",
        "payload": {"takeover_active": True}
    })
    return {"status": "paused_by_user"}

@app.post("/api/takeover/release")
async def release_control():
    takeover_manager.release_control()
    state_tracker.takeover_active = False
    await broadcast_event({
        "event_type": "takeover",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "task_id": state_tracker.task_id,
        "message": "User released control. AI resuming execution...",
        "payload": {"takeover_active": False}
    })
    return {"status": "resumed"}

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
    
    if req.provider.lower() == "local":
        current_model_provider = LocalModelProvider(model_name=req.model_name)
    elif req.provider.lower() == "api":
        current_model_provider = ApiModelProvider(model_name=req.model_name)
    else:
        raise HTTPException(status_code=400, detail="Invalid provider. Choose 'local' or 'api'")
    
    planner = RuleBasedPlanner(current_model_provider)
    agent_loop.planner = planner
    
    return {"status": "model_updated", "provider": req.provider, "model_name": req.model_name}

@app.get("/api/config/permission")
async def get_permissions():
    return policy_manager.get_all_policies()

@app.post("/api/config/permission")
async def configure_permission(req: PolicyConfigRequest):
    policy_manager.update_policy(req.scope, req.level)
    return {"status": "policy_updated", "scope": req.scope, "level": req.level}

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

    async def serve(self, sockets=None):
        # Bind and setup
        await self.startup(sockets=sockets)
        
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
            
        if not self.should_exit:
            await self.main_loop()
        await self.shutdown()

async def start_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = CustomUvicornServer(config)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        pass
