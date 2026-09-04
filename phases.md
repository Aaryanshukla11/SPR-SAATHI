
# Development Constitution / Mandatory Instructions

# SPR SAATHI — Development Phases & Execution Roadmap

## 1. Purpose of This Document

This document defines the mandatory development roadmap for SPR SAATHI.

SPR SAATHI must be developed as a **general-purpose AI operating environment and autonomous Windows computer agent**, not as a collection of isolated automation scripts.

The system must ultimately allow a user to provide a high-level natural-language goal, after which SPR SAATHI should intelligently determine:

1. What the user wants.
2. What information is required.
3. Which capabilities are required.
4. Which tools, skills, applications, models, or specialists should be used.
5. How the task should be executed.
6. How the result should be verified.
7. How failures should be handled.
8. When human clarification or permission is required.

The user should primarily describe **what they want**, not provide detailed instructions about **how the computer should perform the task**.

---

# 2. Mandatory Development Rules

The phases in this document must be followed in sequence unless a documented dependency requires otherwise.

Antigravity or any other development agent working on this repository must follow these rules:

### Rule 1 — Do Not Skip Architecture

Before implementing a feature, verify that it aligns with `ARCHITECTURE.md`.

Do not introduce isolated shortcuts that conflict with the system architecture.

---

### Rule 2 — Do Not Fake Completion

A feature must not be marked complete merely because:

* The code compiles.
* No exception occurs.
* A tool returns `"success"`.
* A mocked unit test passes.
* The UI displays a successful state.

Where real-world behavior is involved, real-world verification is required.

---

### Rule 3 — Fix Root Causes

Do not apply superficial patches.

When a problem is discovered:

1. Reproduce it.
2. Trace the complete execution path.
3. Identify the actual root cause.
4. Implement a robust solution.
5. Add regression tests.

---

### Rule 4 — Preserve Existing Working Functionality

Before modifying a major component:

1. Understand its existing responsibilities.
2. Identify dependent components.
3. Avoid unnecessary rewrites.
4. Run regression tests after modification.

---

### Rule 5 — Prefer Structured Interfaces Over Screen Automation

The preferred execution hierarchy is:

```text
Application API
        ↓
Structured File/API Access
        ↓
Application Automation Interface
        ↓
Accessibility Interface
        ↓
Browser DOM
        ↓
Computer Vision
        ↓
Mouse and Keyboard Automation
```

Raw screen automation should not be the default solution when a more reliable structured method exists.

---

### Rule 6 — Every Important Action Requires Verification

The system must distinguish between:

```text
Action Executed
```

and:

```text
User Goal Successfully Achieved
```

A successful tool call does not automatically mean the task succeeded.

---

### Rule 7 — No Infinite Retries

Every retry mechanism must have:

* A retry limit.
* A reason for retrying.
* A verification step.
* A failure exit condition.

---

### Rule 8 — Document Major Changes

Major architectural decisions, new subsystems, and significant behavioral changes must be reflected in the appropriate documentation.

---

# 3. Phase 0 — Architecture and Project Foundation

## Vision

Create a stable architectural foundation capable of supporting a long-term, complex AI agent.

## Objectives

Establish clear boundaries between:

* Desktop application.
* Agent backend.
* Models.
* Tools.
* Permissions.
* Memory.
* Workspace.
* Skills.
* Verification.
* External specialists.

## Required Work

* Electron application architecture.
* React frontend.
* Python backend.
* FastAPI server.
* REST communication.
* WebSocket event streaming.
* Agent lifecycle.
* Backend process management.
* Shared schemas.
* Configuration management.
* Basic logging.

## Expected Outcome

The desktop application and backend communicate reliably and can safely host the future agent system.

## Phase Completion Criteria

* Electron reliably starts the backend.
* Backend shutdown is handled correctly.
* Frontend reconnects appropriately.
* API contracts are documented.
* WebSocket communication is stable.

## Required Testing

* Startup tests.
* Shutdown tests.
* Backend crash handling.
* WebSocket reconnection.
* API contract validation.
* Real Windows application lifecycle testing.

---

# 4. Phase 1 — Core Agent Execution Engine

## Vision

Build the central intelligence loop that manages autonomous task execution.

## Required Components

### Task Manager

Responsible for:

* Creating tasks.
* Assigning task IDs.
* Tracking task status.
* Cancelling tasks.
* Resuming paused tasks.

### Planner

Converts user goals into structured plans.

### Agent Loop

The core loop should follow:

```text
UNDERSTAND
    ↓
OBSERVE
    ↓
PLAN
    ↓
SELECT ACTION
    ↓
CHECK PERMISSION
    ↓
EXECUTE
    ↓
VERIFY
    ↓
UPDATE STATE
    ↓
REPLAN IF REQUIRED
```

### Action System

Every action must have:

* Action ID.
* Task ID.
* Action type.
* Arguments.
* Status.
* Timestamp.
* Result.
* Verification status.

## Expected Outcome

The agent can reliably execute multi-step tasks while maintaining task state.

## Required Testing

* Multi-step task tests.
* Action ordering tests.
* Cancellation tests.
* Pause/resume tests.
* Duplicate execution tests.
* Async race-condition tests.

---

# 5. Phase 2 — Reliable Computer Interaction

## Vision

Create reliable low-level interaction with Windows.

This phase is foundational because every higher-level computer capability depends on reliable input and window control.

## Required Capabilities

### Keyboard

* Text typing.
* Unicode support.
* Long text support.
* Newlines.
* Punctuation.
* Keyboard shortcuts.
* Key presses.

Keyboard actions must be serialized to prevent event interleaving.

---

### Mouse

* Click.
* Double click.
* Drag.
* Scroll.
* Position validation.

---

### Window Management

* Launch application.
* Detect application readiness.
* Find windows.
* Focus windows.
* Verify foreground state.

---

### Input Coordination

Keyboard, mouse, clipboard, and focus operations must be coordinated to prevent race conditions.

## Expected Outcome

The agent can reliably interact with ordinary Windows applications.

## Required Testing

### Automated Tests

* Tool tests.
* Validation tests.
* Permission tests.
* Concurrency tests.
* Partial failure tests.

### Real Runtime Tests

* Notepad.
* Paint.
* File Explorer.
* Multiple windows.
* Focus switching.
* Long text.
* Unicode text.
* Repeated input operations.

---

# 6. Phase 3 — Unified Perception and Environment Understanding

## Vision

The agent must understand its environment rather than blindly interacting with pixels.

## Required Perception Sources

The perception layer should combine:

* Screenshots.
* Active window information.
* Window hierarchy.
* Running processes.
* Accessibility information.
* File-system state.
* Browser DOM.
* Application metadata.
* User-provided files.

## Perception Priority

Use the most reliable source available:

```text
Structured Application Data
        ↓
Application APIs
        ↓
Accessibility Information
        ↓
Browser DOM
        ↓
Window Metadata
        ↓
Vision Analysis
        ↓
Raw Screen Coordinates
```

## Expected Outcome

The agent has a structured representation of the current environment.

## Required Testing

* Active window detection.
* Application detection.
* Screen changes.
* File-system changes.
* Browser-state detection.
* Real application observation.

---

# 7. Phase 4 — Verification and Failure Recovery

## Vision

SPR SAATHI must verify that it actually completed the user's requested goal.

## Verification Levels

### Tool Verification

Did the tool execute?

### Application Verification

Did the target application respond correctly?

### File Verification

Was the correct file created or modified?

### Data Verification

Does the output contain the expected data?

### Visual Verification

Does the screen contain the expected result?

### Goal Verification

Did the final result satisfy the user's request?

## Failure Recovery

The system should classify failures such as:

* Tool failure.
* Application failure.
* Permission failure.
* Model failure.
* File failure.
* Network failure.
* Verification failure.
* Timeout.

Possible recovery strategies:

```text
Observe Again
    ↓
Retry Safely
    ↓
Alternative Tool
    ↓
Alternative Skill
    ↓
Replan
    ↓
Ask User
    ↓
Stop
```

## Expected Outcome

The agent stops falsely claiming that tasks succeeded.

## Required Testing

* Intentional failures.
* Incorrect tool results.
* Application crashes.
* Missing files.
* Failed verification.
* Recovery limits.

---

# 8. Phase 5 — Skills and Capability Framework

## Vision

Move beyond individual mouse and keyboard actions.

## Tool vs Skill

A tool is atomic:

```text
mouse_click
keyboard_type
launch_app
read_file
```

A skill is a reusable capability:

```text
create_excel_report
modify_document
research_topic
organize_files
analyze_dataset
```

## Required Skill System

Every skill should define:

* Name.
* Description.
* Input schema.
* Output schema.
* Required permissions.
* Required tools.
* Verification strategy.
* Fallback strategy.

## Expected Outcome

The agent can select higher-level capabilities instead of manually constructing every workflow from low-level actions.

## Required Testing

* Skill discovery.
* Skill execution.
* Tool orchestration.
* Skill failures.
* End-to-end workflows.

---

# 9. Phase 6 — Workspace and File Intelligence

## Vision

Enable SPR SAATHI to intelligently work with the user's files.

## Workspace Manager

Track:

* User uploads.
* Existing files.
* Temporary files.
* Generated files.
* Modified files.
* Intermediate artifacts.
* Final deliverables.

## File Intelligence

The system should:

* Search files.
* Identify likely matches.
* Read metadata.
* Understand file types.
* Track file origins.
* Track modifications.

## Example

User:

> "Open the presentation I worked on last week and change the second section."

The system should attempt to:

1. Search relevant locations.
2. Identify likely presentation files.
3. Use memory/history where appropriate.
4. Ask the user only when ambiguity remains.

## Required Testing

* File search.
* Multiple matching files.
* File modifications.
* Artifact tracking.
* Upload handling.

---

# 10. Phase 7 — Document and Productivity Intelligence

## Vision

Enable useful real-world work with structured documents.

## Excel

* Create spreadsheets.
* Modify spreadsheets.
* Analyze data.
* Generate formulas.
* Create charts.
* Validate outputs.

## Word

* Create documents.
* Edit existing documents.
* Format content.
* Extract information.

## PowerPoint

* Create presentations.
* Modify slides.
* Organize content.

## Principle

Prefer structured document libraries or APIs instead of screen automation.

## Required Testing

* Create.
* Modify.
* Save.
* Reopen.
* Compare content.
* Verify output.

---

# 11. Phase 8 — Memory and Conversation System

## Vision

Give SPR SAATHI persistent contextual intelligence.

## Memory Types

### Conversation History

Stores previous conversations.

### Short-Term Context

Stores information relevant to the active task.

### Long-Term Memory

Stores useful information across sessions.

### Preference Memory

Examples:

* Preferred applications.
* Working style.
* Output preferences.

### Project Memory

Stores:

* Project decisions.
* Previous work.
* Important constraints.
* Architecture decisions.

## Memory Controls

Users must be able to:

* View memory.
* Delete memory.
* Correct memory.
* Disable memory where appropriate.

## Required Testing

* Memory creation.
* Retrieval.
* Relevance.
* Conflict handling.
* Deletion.
* Cross-session persistence.

---

# 12. Phase 9 — Context Builder

## Vision

Give the model the right information at the right time.

## Context Sources

* Current user request.
* Conversation history.
* Relevant memories.
* Current task.
* Task history.
* Workspace files.
* Environment state.
* Screen observation.
* Specialist results.

## Required Behavior

The system should not blindly send all available information to the model.

It should retrieve only relevant context.

## Required Testing

* Context relevance.
* Large history.
* Retrieval accuracy.
* Privacy boundaries.

---

# 13. Phase 10 — Chatbot Mode and Agent Mode

## Vision

Provide two clearly defined experiences.

## Chatbot Mode

For:

* Questions.
* Conversation.
* Explanations.
* Analysis.
* Brainstorming.

## SPR SAATHI Agent Mode

For:

* Computer control.
* File work.
* Autonomous tasks.
* Multi-step execution.
* Verification.

## UI Requirement

The interface should provide a clear switch between:

```text
CHAT
↔
SPR SAATHI
```

The modes may share memory and conversation context where appropriate, but their execution behavior must remain distinct.

---

# 14. Phase 11 — Multi-Model Intelligence

## Vision

SPR SAATHI should not depend permanently on one model.

## Model Router

Select models based on:

* Task complexity.
* Reasoning requirements.
* Vision requirements.
* Speed.
* Cost.
* Privacy.
* Local hardware.
* Context requirements.

## Example

```text
Simple Question
→ Fast Model

Complex Planning
→ Reasoning Model

Private File Analysis
→ Local Model

Visual Task
→ Vision Model

Coding Task
→ Coding Specialist
```

## Required Testing

* Routing accuracy.
* Provider failure.
* Fallback.
* Local/cloud switching.

---

# 15. Phase 12 — Specialist Delegation and KAIRO-AI Integration

## Vision

SPR SAATHI should orchestrate specialized systems.

## Specialist Areas

* Coding.
* Research.
* Data analysis.
* Vision.
* Documents.

## KAIRO-AI Integration

Coding tasks should be delegable to KAIRO-AI.

Example:

```text
User Request
      ↓
SPR SAATHI understands task
      ↓
Coding work detected
      ↓
Delegate to KAIRO-AI
      ↓
Receive result
      ↓
Verify result
      ↓
Present to user
```

## Required Testing

* Delegation.
* Result handoff.
* Specialist failure.
* Coding workflow.

---

# 16. Phase 13 — Browser and Research Capabilities

## Vision

Enable safe access to current information.

## Required Capabilities

* Web search.
* Browser navigation.
* Research.
* Multi-source comparison.
* Source tracking.
* Download management.

## Required Testing

* Search.
* Navigation.
* Source verification.
* Browser failures.
* Download verification.

---

# 17. Phase 14 — Advanced Vision and Image Workflows

## Vision

Enable intelligent visual understanding and image work.

## Capabilities

* Image understanding.
* UI understanding.
* Image editing.
* Visual task execution.
* Visual verification.

## Important Principle

The agent must not claim a graphical task succeeded merely because mouse actions were executed.

The resulting visual output must be verified.

## Required Testing

* Image understanding.
* UI analysis.
* Graphical tasks.
* Image modification.
* Output verification.

---

# 18. Phase 15 — Human-in-the-Loop Intelligence

## Vision

The agent should recognize uncertainty.

## Ask the User When

* Multiple files match.
* The request is ambiguous.
* Important information is missing.
* Instructions conflict.
* A destructive operation is uncertain.

## Required Workflow

```text
Uncertainty
    ↓
Pause Task
    ↓
Ask User
    ↓
Receive Answer
    ↓
Update Context
    ↓
Resume Task
```

---

# 19. Phase 16 — Security and Privacy

## Vision

Increase autonomy without removing user control.

## Security Areas

* File permissions.
* Application control.
* Terminal execution.
* Browser actions.
* Network access.
* Memory access.
* Sensitive data.

## Required Testing

* Allow.
* Deny.
* Permission persistence.
* Sensitive operations.
* Audit logs.

---

# 20. Phase 17 — Observability and Diagnostics

## Vision

Every important task should be debuggable.

## Track

* Task IDs.
* Action IDs.
* Model decisions.
* Tool calls.
* Observations.
* Verification.
* Recovery attempts.
* Errors.
* Performance.

## Required Testing

* Complete traces.
* Error propagation.
* Correlation IDs.
* Long-running logs.

---

# 21. Phase 18 — End-to-End Autonomous Workflows

## Vision

Combine all subsystems into real user workflows.

## Example Task

> "Take this data, create an Excel report, add charts and save the final file."

The agent should:

1. Understand the goal.
2. Access the data.
3. Select the correct capability.
4. Create the output.
5. Add calculations.
6. Generate charts.
7. Save the file.
8. Verify it.
9. Deliver the result.

## Required Testing

* Full workflows.
* Cross-capability tasks.
* User interruptions.
* Failure recovery.

---

# 22. Phase 19 — Production Hardening

## Vision

Prepare the system for long-term real-world usage.

## Required Work

* Performance optimization.
* Memory monitoring.
* Crash recovery.
* Backend recovery.
* Task persistence.
* Graceful shutdown.
* Stress testing.

## Required Testing

* Long-duration runtime.
* High task volume.
* Backend crashes.
* Model failures.
* Memory leaks.
* Recovery testing.

---

# 23. Global Phase Completion Standard

No phase may be marked as complete until all applicable requirements have passed:

```text
Implementation Complete
        ↓
Code Review
        ↓
Automated Tests Pass
        ↓
Integration Tests Pass
        ↓
Real Runtime Tests Pass
        ↓
Failure Cases Tested
        ↓
Regression Tests Pass
        ↓
Documentation Updated
        ↓
Phase Approved
```

---

# 24. Final Vision

The final version of SPR SAATHI should be capable of receiving a natural-language objective such as:

> "Analyze these files, create a report, update the presentation, email the result and let me know when everything is finished."

The user should not need to specify:

* Which application to open.
* Where the file is located.
* Which mouse buttons to press.
* How to format the document.
* Which model should perform the work.

SPR SAATHI should intelligently determine the appropriate approach while remaining transparent, verifiable, secure, and under the user's control.

---

