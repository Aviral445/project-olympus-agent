import sys
import os
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to path to locate agents module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.core_graph import app as graph_app

server = FastAPI(
    title="Olympus SRE Agent API",
    description="Backend API and WebSocket stream for autonomous code patching",
    version="1.0.0"
)

# Allow CORS for future frontend integration
server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunAgentRequest(BaseModel):
    bug_description: str = "Initial bug trace"
    target_file: str = ""

@server.get("/")
def health_check():
    return {
        "status": "online",
        "system": "Project Olympus SRE Engine",
        "version": "1.0.0"
    }

@server.websocket("/ws/run-agent")
async def websocket_agent_run(websocket: WebSocket):
    """
    Streams live LangGraph execution state, patch attempts, 
    and sandbox verification logs over WebSocket.
    """
    await websocket.accept()
    await websocket.send_json({
        "event": "connected",
        "message": "Connected to Olympus SRE Execution Engine"
    })

    try:
        data = await websocket.receive_text()
        params = json.loads(data) if data else {}
        
        initial_state = {
            "bug_description": params.get("bug_description", "Triggered via WebSocket"),
            "proposed_fix": "",
            "test_result": "Initial run required",
            "attempt_count": 0,
            "target_file": params.get("target_file", ""),
            "history": []
        }

        await websocket.send_json({
            "event": "start",
            "message": "Starting Project Olympus State Machine...",
            "state": initial_state
        })

        # Run the graph and stream steps asynchronously
        loop = asyncio.get_running_loop()

        def execute_step(state):
            return graph_app.invoke(state)

        # Run execution in threadpool to prevent blocking the async socket loop
        final_state = await loop.run_in_executor(None, execute_step, initial_state)

        await websocket.send_json({
            "event": "complete",
            "message": "Execution finished cleanly!",
            "final_state": {
                "attempt_count": final_state.get("attempt_count"),
                "test_result": final_state.get("test_result"),
                "history": final_state.get("history")
            }
        })

    except WebSocketDisconnect:
        print("🔌 Client disconnected from WebSocket stream.")
    except Exception as e:
        await websocket.send_json({
            "event": "error",
            "error": str(e)
        })
    finally:
        await websocket.close()