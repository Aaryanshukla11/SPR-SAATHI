import asyncio
import sys
import os
import datetime
import time
import uvicorn
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import agent components
from agent.core.state import StateTracker
from agent.core.task_manager import TaskManager
from agent.core.planner import RuleBasedPlanner
from agent.core.executor import ToolExecutor
from agent.core.loop import AgentLoop
from agent.tools import get_all_tools
from agent.permissions.policies import PolicyManager
from agent.permissions.broker import PermissionBroker
from agent.control.takeover import TakeoverManager
from agent.models.local import LocalModelProvider
from agent.models.api import ApiModelProvider
from agent.core import win32_utils
from agent.core.memory import MEMORY_MANAGER, MemoryType, MemoryItem
from agent.core.workspace import WORKSPACE_MANAGER, FileOrigin, FileType
from agent.skills import SKILL_REGISTRY, get_skill_registry
from agent.core.specialists import SPECIALIST_DELEGATOR, SpecialistType
from agent.core.production_hardening import MEMORY_MONITOR, CRASH_RECOVERY
import uuid
from agent.models.router import ModelRouter, PrivacyLevel
from agent.core.conversation_store import CONVERSATION_STORE

# Initialize core modules
state_tracker = StateTracker()
task_manager = TaskManager(state_tracker=state_tracker)
policy_manager = PolicyManager()
permission_broker = PermissionBroker(policy_manager, state_tracker)
takeover_manager = TakeoverManager()

# Default Model Provider (local Ollama by default if no cloud API keys present)
if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
    current_model_provider = ApiModelProvider(model_name="Gemini 3.5 Flash")
else:
    current_model_provider = LocalModelProvider(model_name="qwen2.5:latest")
model_router = ModelRouter(default_provider=current_model_provider)
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
    broadcast_callback=broadcast_event,
    task_manager=task_manager
)

# Pydantic Schemas matching the shared contracts
import datetime
class StartTaskRequest(BaseModel):
    task: str
    attachments: Optional[List[Dict[str, Any]]] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None
    system_instruction: Optional[str] = None
    session_id: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None

class CreateConversationRequest(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None

class UpdateConversationRequest(BaseModel):
    title: str

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

class QuestionResponseRequest(BaseModel):
    response: str

class MemoryCreateRequest(BaseModel):
    key: str
    content: str
    memory_type: str = "preference_memory"
    tags: Optional[List[str]] = None

class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 5

class SkillExecuteRequest(BaseModel):
    parameters: Dict[str, Any]

class SpecialistDelegateRequest(BaseModel):
    task: str
    context: Optional[Dict[str, Any]] = None

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/state")
async def get_state():
    return state_tracker.to_dict()

@app.post("/api/context/upload")
async def upload_context_endpoint(files: List[UploadFile] = File(...)):
    from agent.core.file_extractor import process_uploaded_file
    workspace_dir = os.path.join(WORKSPACE_MANAGER.workspace_root, "uploads")
    os.makedirs(workspace_dir, exist_ok=True)
    
    results = []
    for file in files:
        contents = await file.read()
        item = process_uploaded_file(file.filename, contents)
        
        # Save to disk for persistence and workspace integration
        dest_path = os.path.join(workspace_dir, file.filename)
        try:
            with open(dest_path, "wb") as f:
                f.write(contents)
            item["file_path"] = dest_path
            WORKSPACE_MANAGER.register_file(
                dest_path,
                origin=FileOrigin.USER_UPLOAD,
                task_id=state_tracker.task_id
            )
        except Exception:
            item["file_path"] = ""
            
        results.append(item)
        
    return {"status": "success", "files": results}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    
    session_id = req.session_id or f"conv_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
    active_model_name = getattr(current_model_provider, "model_name", "unknown")
    
    user_display_msg = user_msg
    image_base64 = None
    if req.attachments:
        att_names = [a.get("filename") or a.get("name", "file") for a in req.attachments]
        user_display_msg = f"[Attached: {', '.join(att_names)}]\n{user_msg}"
        
        context_blocks = []
        for att in req.attachments:
            fname = att.get("filename") or att.get("name", "file")
            ftype = att.get("file_type") or att.get("type", "unknown")
            size_s = att.get("size_str", "")
            txt = (att.get("extracted_text") or "").strip()
            
            if att.get("image_base64") and not image_base64:
                image_base64 = att["image_base64"]
                
            if txt:
                context_blocks.append(f"--- [File: {fname} | Type: {ftype} | Size: {size_s}] ---\n{txt}")
                
        if context_blocks:
            attached_context = (
                "\n\n=== USER ATTACHED CONTEXT FILES ===\n"
                "The user has uploaded the following files/documents for you to analyze, understand, and use to answer their request:\n\n"
                + "\n\n".join(context_blocks) +
                "\n===================================\n"
            )
            default_system_prefix = attached_context
        else:
            default_system_prefix = ""
    else:
        default_system_prefix = ""

    CONVERSATION_STORE.append_message(session_id, "user", user_display_msg, model=active_model_name)

    await broadcast_event({
        "event_type": "chat.started",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task_id": None,
        "message": f"User: {user_msg[:100]}",
        "payload": {"message": user_msg, "session_id": session_id}
    })

    from agent.core.memory import MEMORY_MANAGER
    MEMORY_MANAGER.record_conversation_turn("user", user_display_msg, session_id=session_id)

    default_system = (
        "You are ORBIT in Chatbot Mode — a highly capable, knowledgeable, and helpful AI assistant (similar to ChatGPT).\n"
        "Your role is to assist the user by having natural conversations, answering questions across any topic, explaining concepts clearly, "
        "providing thoughtful coding help and debugging, and formatting answers in clean GitHub-flavored Markdown with code blocks where helpful.\n"
        "IMPORTANT: When the user provides context files (PDF, DOC, text, code, or images), carefully study the attached content and answer thoroughly and accurately based on it.\n"
        "In this mode, you are operating strictly as a conversational chatbot. You do not control the user's computer or execute OS tools."
    )
    sys_instruction = (req.system_instruction or default_system) + default_system_prefix

    try:
        relevant_mems = MEMORY_MANAGER.retrieve_relevant(user_msg, limit=3)
        if relevant_mems:
            mem_text = "\n".join(f"- {m.key}: {m.content}" for m, _ in relevant_mems)
            sys_instruction += f"\n\n=== RELEVANT USER MEMORIES ===\n{mem_text}"
    except Exception:
        pass

    if req.history:
        history_lines = []
        for h in req.history:
            role_label = "User" if h.role == "user" else "Assistant"
            history_lines.append(f"{role_label}: {h.content}")
        history_lines.append(f"User: {user_msg}")
        full_prompt = "\n\n".join(history_lines)
    else:
        full_prompt = user_msg

    try:
        response_obj = await current_model_provider.generate(
            prompt=full_prompt,
            system_instruction=sys_instruction,
            image_base64=image_base64
        )
        response_text = response_obj.text if hasattr(response_obj, "text") else str(response_obj)
        MEMORY_MANAGER.record_conversation_turn("assistant", response_text, session_id=session_id)
        CONVERSATION_STORE.append_message(session_id, "assistant", response_text, model=active_model_name)

        await broadcast_event({
            "event_type": "chat.response",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": None,
            "message": "Chat response generated.",
            "payload": {"response": response_text, "session_id": session_id}
        })

        return {
            "status": "success",
            "response": response_text,
            "model": active_model_name,
            "session_id": session_id
        }
    except Exception as e:
        err_msg = str(e)
        if "API_CREDENTIALS_MISSING" in err_msg:
            friendly_err = "⚠️ **API Key Missing**: The selected cloud model requires an API key. Please configure your API key in **Settings**, or select one of your local installed Ollama models (such as `Qwen 2.5 7B` or `Llama 3.2 Vision`) from the model dropdown."
        elif "MODEL_UNAVAILABLE" in err_msg or "Connection refused" in err_msg or "11434" in err_msg:
            friendly_err = "⚠️ **Local Model Unavailable**: Could not connect to local Ollama on port 11434. Please ensure Ollama is running (`ollama serve`)."
        else:
            friendly_err = f"⚠️ **Chatbot Error**: {err_msg}"

        CONVERSATION_STORE.append_message(session_id, "assistant", friendly_err, model=active_model_name)

        await broadcast_event({
            "event_type": "chat.error",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": None,
            "message": f"Chat error: {err_msg}",
            "payload": {"error": friendly_err, "session_id": session_id}
        })
        return {
            "status": "error",
            "response": friendly_err,
            "model": active_model_name,
            "session_id": session_id
        }

@app.post("/api/chat/clear")
async def clear_chat_endpoint():
    await broadcast_event({
        "event_type": "chat.cleared",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "task_id": None,
        "message": "Chat history cleared.",
        "payload": {}
    })
    return {"status": "cleared"}

@app.get("/api/conversations")
async def list_conversations_endpoint():
    return {"conversations": CONVERSATION_STORE.list_conversations()}

@app.get("/api/conversations/{session_id}")
async def get_conversation_endpoint(session_id: str):
    conv = CONVERSATION_STORE.get_conversation(session_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"conversation": conv}

@app.post("/api/conversations")
async def create_conversation_endpoint(req: Optional[CreateConversationRequest] = None):
    title = req.title if req else None
    model = req.model if req else getattr(current_model_provider, "model_name", "unknown")
    conv = CONVERSATION_STORE.create_conversation(title=title, model=model)
    return {"status": "created", "conversation": conv}

@app.patch("/api/conversations/{session_id}")
async def update_conversation_endpoint(session_id: str, req: UpdateConversationRequest):
    ok = CONVERSATION_STORE.update_title(session_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "updated"}

@app.delete("/api/conversations/{session_id}")
async def delete_conversation_endpoint(session_id: str):
    ok = CONVERSATION_STORE.delete_conversation(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}

@app.delete("/api/conversations")
async def clear_conversations_endpoint():
    CONVERSATION_STORE.clear_all()
    return {"status": "cleared"}

@app.post("/api/task/start")
async def start_task(req: StartTaskRequest):
    if state_tracker.status not in ["idle", "stopped", "completed", "error", "failed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Agent is already busy running a task.")
    
    task_description = req.task
    if req.attachments:
        att_lines = []
        for att in req.attachments:
            fname = att.get("filename") or att.get("name", "file")
            fpath = att.get("file_path", "")
            ftxt = (att.get("extracted_text") or "").strip()
            if fpath:
                info_str = f" | Details: {ftxt}" if ftxt else ""
                att_lines.append(f"- File: {fname} (Saved at: {fpath}{info_str})")
            elif ftxt:
                att_lines.append(f"- File: {fname}:\n{ftxt[:400]}")
        if att_lines:
            task_description = f"{task_description}\n\n[Context Files Provided]:\n" + "\n".join(att_lines)
            
    agent_loop.start_task(task_description)
    return {"status": "started", "task_id": state_tracker.task_id}

@app.post("/api/task/stop")
async def stop_task():
    agent_loop.stop_task()
    return {"status": "stopped"}

@app.post("/api/task/respond_question")
async def respond_question_endpoint(req: QuestionResponseRequest):
    if not agent_loop:
        raise HTTPException(status_code=500, detail="Agent loop not initialized.")
    success = agent_loop.submit_user_response(req.response)
    if not success:
        raise HTTPException(status_code=400, detail="No active question waiting for response.")
    return {"status": "success", "response": req.response}

@app.get("/api/tasks")
async def list_tasks_endpoint():
    return task_manager.list_tasks()

@app.get("/api/tasks/{task_id}")
async def get_task_endpoint(task_id: str):
    t = task_manager.get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found.")
    return t.to_dict()

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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
            models_list = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if not name:
                    continue
                details = m.get("details", {})
                size_bytes = m.get("size", 0)
                size_gb = round(size_bytes / (1024 * 1024 * 1024), 1)
                param_size = details.get("parameter_size", "")
                family = details.get("family", "")
                caps = m.get("capabilities", [])
                is_vision = "vision" in caps or "vision" in name.lower() or "llava" in name.lower() or "mllama" in family.lower() or "vl" in name.lower()
                is_embedding = "embedding" in caps or "embed" in name.lower()
                
                # Format a user-friendly specs string
                specs_parts = [f"Size: {size_gb} GB"]
                if param_size:
                    specs_parts.append(f"Params: {param_size}")
                if is_vision:
                    specs_parts.append("Vision Supported")
                if family:
                    specs_parts.append(f"Family: {family}")
                specs_str = " • ".join(specs_parts)

                models_list.append({
                    "name": name,
                    "tag": name,
                    "size_gb": size_gb,
                    "parameter_size": param_size,
                    "family": family,
                    "capabilities": caps,
                    "is_vision": is_vision,
                    "is_embedding": is_embedding,
                    "specs": specs_str
                })
            return {
                "status": "success", 
                "models": [m["name"] for m in models_list],
                "model_details": models_list
            }
    except Exception as e:
        return {"status": "error", "message": str(e), "models": [], "model_details": []}

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

# ============================================================================
# Phase 8: Memory & Context Endpoints
# ============================================================================
@app.get("/api/memory")
async def list_memories_endpoint(type: Optional[str] = None):
    mem_type = None
    if type:
        try:
            mem_type = MemoryType(type)
        except ValueError:
            pass
    return MEMORY_MANAGER.view_all_memories(mem_type)

@app.post("/api/memory")
async def create_or_update_memory_endpoint(req: MemoryCreateRequest):
    try:
        mem_type = MemoryType(req.memory_type)
    except ValueError:
        mem_type = MemoryType.PREFERENCE_MEMORY
    item = MEMORY_MANAGER.add_memory(
        memory_type=mem_type,
        key=req.key,
        content=req.content,
        tags=req.tags or []
    )
    return {"status": "success", "memory": item.to_dict()}

@app.delete("/api/memory/{memory_id}")
async def delete_memory_endpoint(memory_id: str):
    success = MEMORY_MANAGER.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"status": "deleted", "id": memory_id}

@app.post("/api/memory/clear")
async def clear_all_memories_endpoint():
    MEMORY_MANAGER.clear_all()
    return {"status": "cleared"}

@app.post("/api/memory/search")
async def search_memories_endpoint(req: MemorySearchRequest):
    results = MEMORY_MANAGER.retrieve_relevant(req.query, limit=req.limit)
    return [
        {"memory": m.to_dict(), "relevance_score": score}
        for m, score in results
    ]

# ============================================================================
# Phase 6: Workspace & File Intelligence Endpoints
# ============================================================================
@app.get("/api/workspace/files")
async def list_workspace_files_endpoint():
    WORKSPACE_MANAGER.search_files("")
    return [m.to_dict() for m in WORKSPACE_MANAGER.tracked_files.values()]

@app.post("/api/workspace/upload")
async def upload_workspace_file_endpoint(file: UploadFile = File(...)):
    workspace_dir = WORKSPACE_MANAGER.workspace_root
    os.makedirs(workspace_dir, exist_ok=True)
    dest_path = os.path.join(workspace_dir, file.filename)
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)
    meta = WORKSPACE_MANAGER.register_file(
        dest_path,
        origin=FileOrigin.USER_UPLOAD,
        task_id=state_tracker.task_id
    )
    return {"status": "uploaded", "file": meta.to_dict() if meta else {}}

@app.get("/api/workspace/search")
async def search_workspace_files_endpoint(query: str = "", limit: int = 10):
    results = WORKSPACE_MANAGER.search_files(query=query, max_results=limit)
    return [
        {"file": meta.to_dict(), "relevance_score": score}
        for meta, score in results
    ]

# ============================================================================
# Phase 5: Skills & Capability Registry Endpoints
# ============================================================================
@app.get("/api/skills")
async def list_skills_endpoint():
    registry = get_skill_registry()
    return registry.list_skills()

@app.post("/api/skills/{skill_name}/execute")
async def execute_skill_endpoint(skill_name: str, req: SkillExecuteRequest):
    registry = get_skill_registry()
    skill = registry.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found.")
    try:
        result = await skill.execute(req.parameters)
        return {
            "status": "success" if result.success else "failed",
            "result": {
                "skill_name": result.skill_name,
                "success": result.success,
                "output": result.output,
                "steps_executed": result.steps_executed,
                "verification_details": result.verification_details,
                "error": result.error
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Phase 12: Specialist Delegation & KAIRO-AI Endpoints
# ============================================================================
@app.get("/api/specialists")
async def list_specialists_endpoint():
    return [
        {
            "name": s.name,
            "specialist_type": s.specialist_type.value,
            "description": s.description
        }
        for s in SPECIALIST_DELEGATOR._specialists.values()
    ]

@app.post("/api/specialists/delegate")
async def delegate_specialist_endpoint(req: SpecialistDelegateRequest):
    res = await SPECIALIST_DELEGATOR.delegate_task(req.task, req.context)
    if not res:
        return {"status": "no_specialist_found", "message": "No specialist capable of handling this task"}
    return {
        "status": "success" if res.success else "failed",
        "specialist": res.specialist_name,
        "type": res.specialist_type.value,
        "output": res.output,
        "verification_passed": res.verification_passed,
        "code_artifacts": res.code_artifacts,
        "error": res.error
    }

# ============================================================================
# Phase 17: Observability & Diagnostics Endpoints
# ============================================================================
@app.get("/api/trace")
async def get_execution_trace_endpoint():
    if agent_loop and agent_loop.tracer:
        return agent_loop.tracer.get_trace()
    trace_path = "agent_execution_trace.json"
    if os.path.exists(trace_path):
        try:
            import json
            with open(trace_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"task_id": "none", "steps": [], "total_steps": 0}

@app.get("/api/trace/summary")
async def get_trace_summary_endpoint():
    if agent_loop and agent_loop.tracer:
        return agent_loop.tracer.export_diagnostic_summary()
    return {"status": "no_active_trace"}

# ============================================================================
# Phase 19: System Metrics & Health Endpoint
# ============================================================================
@app.get("/api/system/metrics")
async def get_system_metrics_endpoint():
    mem_mb = MEMORY_MONITOR.get_current_memory_mb()
    health = MEMORY_MONITOR.check_memory_health()
    import psutil
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count(logical=True)
    return {
        "status": "healthy",
        "memory": {
            "rss_mb": mem_mb,
            "warning_threshold_mb": MEMORY_MONITOR.warning_threshold_mb,
            "critical_threshold_mb": MEMORY_MONITOR.critical_threshold_mb,
            "health_status": health["status"]
        },
        "system": {
            "cpu_percent": cpu_percent,
            "cpu_count": cpu_count,
            "platform": sys.platform
        },
        "agent": {
            "status": state_tracker.status,
            "active_task_id": state_tracker.task_id,
            "takeover_active": state_tracker.takeover_active,
            "control_state": takeover_manager.control_state
        }
    }

# ============================================================================
# Phase 11: Multi-Model Catalog Endpoint
# ============================================================================
@app.get("/api/models/catalog")
async def get_models_catalog_endpoint():
    catalog = []
    for name, (spec, prov) in model_router._models.items():
        catalog.append({
            "name": spec.name,
            "provider_type": spec.provider_type,
            "capabilities": [c.value for c in spec.capabilities],
            "cost_tier": spec.cost_tier,
            "speed_tier": spec.speed_tier,
            "is_available": spec.is_available,
            "failure_count": spec.failure_count
        })
    return {
        "models": catalog,
        "active_model": getattr(current_model_provider, "model_name", "unknown")
    }

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
