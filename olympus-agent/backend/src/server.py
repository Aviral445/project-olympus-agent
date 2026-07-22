import sys
import os
import asyncio
import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Add src to path for internal imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from utils.db import get_db, PatchLog, init_db
from utils.github_webhook import verify_github_signature, parse_github_event
from agents.core_graph import app as graph_app

# Initialize DB tables on startup
init_db()

server = FastAPI(
    title="Olympus SRE Agent API",
    description="Backend API, WebSockets, and Webhooks for autonomous SRE patching",
    version="1.0.0"
)

# Enable CORS for frontend integration
server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class LogResponse(BaseModel):
    id: int
    target_file: str
    attempt: int
    status: str
    git_diff: str
    error_logs: str
    created_at: str

    class Config:
        from_attributes = True

class RunAgentRequest(BaseModel):
    bug_description: str = "Initial bug trace"
    target_file: str = ""

# --- REST Endpoints ---
@server.get("/")
def health_check():
    return {
        "status": "online",
        "system": "Project Olympus SRE Engine",
        "version": "1.0.0"
    }

@server.get("/api/logs", response_model=List[LogResponse])
def get_all_logs(db: Session = Depends(get_db)):
    """Fetch all historical patch execution logs from the database."""
    logs = db.query(PatchLog).order_by(PatchLog.id.desc()).all()
    
    return [
        LogResponse(
            id=log.id,
            target_file=log.target_file,
            attempt=log.attempt,
            status=log.status,
            git_diff=log.git_diff or "",
            error_logs=log.error_logs or "",
            created_at=str(log.created_at)
        )
        for log in logs
    ]

@server.get("/api/logs/{log_id}", response_model=LogResponse)
def get_log_by_id(log_id: int, db: Session = Depends(get_db)):
    """Fetch a specific patch run log by its ID."""
    log = db.query(PatchLog).filter(PatchLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    
    return LogResponse(
        id=log.id,
        target_file=log.target_file,
        attempt=log.attempt,
        status=log.status,
        git_diff=log.git_diff or "",
        error_logs=log.error_logs or "",
        created_at=str(log.created_at)
    )

# --- GitHub Webhook Endpoint ---
@server.post("/api/webhook/github")
async def github_webhook_listener(request: Request, background_tasks: BackgroundTasks):
    """
    Receives incoming GitHub Webhooks (CI failures, Issue reports)
    and asynchronously executes the LangGraph state machine in the background.
    """
    event_type = request.headers.get("X-GitHub-Event", "ping")
    signature = request.headers.get("X-Hub-Signature-256", "")
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    raw_body = await request.body()

    # Verify HMAC signature if secret is configured
    if webhook_secret and not verify_github_signature(raw_body, webhook_secret, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    payload = await request.json()

    # Ping event check during initial Webhook configuration
    if event_type == "ping":
        return {"status": "pong", "message": "GitHub Webhook successfully configured!"}

    bug_description, target_file, repo_url = parse_github_event(event_type, payload)

    print(f"\n🔔 [GitHub Webhook]: Event '{event_type}' received!")
    print(f"📌 [Issue/Bug Context]: {bug_description}")

    # Helper function to execute background SRE job
    def trigger_agent_job():
        initial_state = {
            "bug_description": bug_description,
            "proposed_fix": "",
            "test_result": bug_description,
            "attempt_count": 0,
            "target_file": target_file,
            "last_diff": "",
            "history": [f"Triggered via GitHub event: {event_type}"]
        }
        graph_app.invoke(initial_state)

    # Queue background execution so GitHub's webhook call returns 202 immediately
    background_tasks.add_task(trigger_agent_job)

    return {
        "status": "accepted",
        "event": event_type,
        "bug_description": bug_description,
        "message": "SRE Agent repair workflow queued in background."
    }

# --- Real-Time Streaming WebSocket Endpoint ---
@server.websocket("/ws/run-agent")
async def websocket_agent_run(websocket: WebSocket):
    """
    Streams live LangGraph execution steps, patch generation,
    and sandbox verification logs over WebSocket.
    """
    await websocket.accept()
    await websocket.send_json({
        "type": "connection",
        "status": "connected",
        "message": "Connected to Olympus SRE Execution Engine"
    })

    try:
        data = await websocket.receive_text()
        params = json.loads(data) if data else {}

        initial_state = {
            "bug_description": params.get("bug_description", "WebSocket initiated repair"),
            "proposed_fix": "",
            "test_result": "Initial run required",
            "attempt_count": 0,
            "target_file": params.get("target_file", ""),
            "last_diff": "",
            "history": []
        }

        await websocket.send_json({
            "type": "state_update",
            "node": "system",
            "message": "Initializing State Machine...",
            "data": initial_state
        })

        # Stream node execution events in real time
        for event in graph_app.stream(initial_state):
            for node_name, state_update in event.items():
                await websocket.send_json({
                    "type": "node_complete",
                    "node": node_name,
                    "attempt": state_update.get("attempt_count", 0),
                    "test_result": state_update.get("test_result", ""),
                    "git_diff": state_update.get("last_diff", ""),
                    "history": state_update.get("history", [])
                })
                await asyncio.sleep(0.1)

        await websocket.send_json({
            "type": "complete",
            "status": "success",
            "message": "Autonomous patch pipeline finished execution."
        })

    except WebSocketDisconnect:
        print("🔌 Client disconnected from WebSocket stream.")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
    finally:
        await websocket.close()