# SPR SAATHI System Architecture (Phase 0)

SPR SAATHI is a desktop AI Computer Agent for Windows 10/11. This document explains the major architectural components, data boundaries, and communication structures established in the foundation (Phase 0).

---

## Component Layout & Responsibilities

The system is split into three main areas to enforce clear boundaries:

```mermaid
graph TD
    subgraph Electron Frontend [desktop/ (Electron + React)]
        UI[React App UI]
        Main[Main Process]
        Preload[Preload Script]
    end

    subgraph Python Backend [agent/ (FastAPI + Python)]
        Server[FastAPI Server]
        Loop[Agent Loop]
        Broker[Permission Broker]
        Planner[Task Planner]
        Executor[Tool Executor]
        Tracker[State Tracker]
        Models[Model Provider Layer]
        Tools[Computer Tools]
    end

    UI <-->|HTTP REST / WebSockets| Server
    Main -->|Spawn / Lifecycle| Server
    Main <-->|IPC| Preload <-->|ContextBridge| UI
    
    Loop --> Tracker
    Loop --> Planner
    Loop --> Executor
    Executor --> Broker
    Broker --> Policies[Permission Policies]
    Executor --> Tools
    Planner --> Models
```

### 1. Desktop UI (`desktop/`)
The desktop environment runs on Electron, React, and TypeScript.
*   **Main Process (`desktop/src/main/index.ts`)**:
    *   Creates a docked BrowserWindow locked to the right side of the monitor (occupying 25-30% of screen width).
    *   Spawns the Python agent backend subprocess on startup.
    *   Captures and resolves the dynamically assigned localhost port printed by Python.
    *   Exposes global controls (e.g. Always-on-top configurations) and cleans up the Python subprocess when Electron exits.
*   **Preload Process (`desktop/src/preload/index.ts`)**:
    *   Exposes a secure and typed bridge (`window.api`) for the React app to retrieve the dynamic backend port and communicate configuration changes.
*   **Renderer Process (`desktop/src/renderer/src/`)**:
    *   Builds a glassmorphic dashboard representing the conversation feeds, the current loop status, step lists, permission configurations, and user controls.
    *   Connects to the Python server over HTTP (for actions) and WebSockets (for live events).

### 2. Python Agent Backend (`agent/`)
The agent backend is a FastAPI server hosting the execution loop and abstract provider components.
*   **FastAPI Server (`agent/main.py`)**:
    *   Binds to a dynamic free port (`port=0`).
    *   Prints `PORT: <port>` to standard output immediately on startup so the Electron main process can parse it.
    *   Exposes REST endpoints (`/api/*`) for client actions and `/ws` for streaming real-time events.
*   **State Tracker (`agent/core/state.py`)**:
    *   Tracks task history, planned steps, active step, takeover, and errors.
*   **Task Planner (`agent/core/planner.py`)**:
    *   Analyzes the active user prompt and current desktop observation, outputting structured execution steps.
*   **Tool Executor (`agent/core/executor.py`)**:
    *   Routes planned tool calls to specific tool classes. Enforces security checking via the Permission Broker prior to launching any tool.
*   **Agent Loop (`agent/core/loop.py`)**:
    *   Controls the `OBSERVE → PLAN → CHECK PERMISSION → ACT → VERIFY → REPLAN` loop.
    *   Handles asynchronous pause states (human takeover) and task cancellations.
*   **Permission Broker (`agent/permissions/`)**:
    *   Checks execution parameters against `policies.py` (allow, deny, prompt).
    *   If policy is `prompt`, pauses the loop and yields a WebSocket event to the Electron UI, blocking execution until the user selects "Allow" or "Deny" from the overlay.
*   **Model Provider Layer (`agent/models/`)**:
    *   Defines abstract completions for both local LLMs (e.g. Llama) and API LLMs (e.g. Gemini).
*   **Computer Tools (`agent/tools/`)**:
    *   Defines abstract base tools (`computer`, `windows`, `filesystem`, `terminal`, `browser`).

---

## Communication Boundaries

### 1. Process Lifecycle
```text
Electron App Starts 
  └── Spawn Python Backend (port=0)
  └── Read stdout -> Find "PORT: XXXXX"
  └── Initialize BrowserWindow (x=Right edge, y=0)
  └── React UI Loads -> Fetch port via IPC -> Connect WebSocket
  └── User exits Electron -> Python killed (will-quit hook)
```

### 2. Data Flow Protocol
All dynamic interactions follow strict request/response shapes defined in `shared/schemas/`:

*   **REST API (Transactional controls)**:
    *   `POST /api/task/start`: Submits a task command.
    *   `POST /api/task/stop`: Safely cancels active loop executions.
    *   `POST /api/takeover/take`: Pauses the agent immediately.
    *   `POST /api/takeover/release`: Resumes agent execution.
    *   `POST /api/permission/respond`: Submits user's security decision (`allow` or `deny`).
    *   `POST /api/config/model`: Swaps the model provider configuration.
    *   `POST /api/config/permission`: Dynamically updates a permission scope's default policy.
*   **WebSocket Events (Real-time streams)**:
    *   Streams status changes, step updates, terminal logs, loop observations, and prompts.

---

## Security Policy Design

The permission policies default to:
1.  **Windows app launching (`windows`)**: `allow`
2.  **Web browsing (`browser`)**: `allow`
3.  **Mouse/Keyboard control (`computer`)**: `prompt`
4.  **Filesystem operations (`filesystem`)**: `prompt`
5.  **Terminal command execution (`terminal`)**: `prompt`

Actions matching `prompt` halt backend execution in a non-blocking asynchronous wait. The user can dynamically reconfigure these rules directly from the Electron dashboard settings.
