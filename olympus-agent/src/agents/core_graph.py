import sys
import os
import time
from typing import Dict, TypedDict, List
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Configure paths and load environment variables
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env')))

from utils.sandbox import run_in_sandbox 

# 1. Define the Global State
class AgentState(TypedDict):
    bug_description: str
    proposed_fix: str
    test_result: str
    attempt_count: int
    history: List[str]

# Pull the single primary key from our secure .env file
API_KEY = os.getenv("GEMINI_API_KEY")

def call_gemini_with_retry(prompt: str, max_retries: int = 3, initial_delay: int = 4) -> str:
    """
    Calls Gemini using a single API key. If the server is overloaded (503/429),
    it applies an exponential backoff (waiting longer between each retry).
    """
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", google_api_key=API_KEY)
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            response = llm.invoke(prompt)
            if isinstance(response.content, list):
                return response.content[0].get("text", response.content).strip()
            return response.content.strip()
        except Exception as e:
            error_msg = str(e)
            # Catch temporary server overloads or rate limits
            if "503" in error_msg or "429" in error_msg:
                if attempt < max_retries - 1:
                    print(f"\n⚠️ [Server Busy]: Gemini returned 503/429. Retrying in {delay}s (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
            raise e

# 2. Define the Nodes
def patch_agent(state: AgentState) -> Dict:
    current_attempts = state.get("attempt_count", 0) + 1
    print(f"\n🤖 [Patch Agent]: Analyzing bug and writing fix (Attempt #{current_attempts})...")
    
    target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
    
    # Read the broken file
    with open(target_file_path, "r") as f:
        current_code = f.read()

    prompt = f"""
    You are an autonomous SRE agent. Your goal is to fix the following broken Python code.
    
    CRITICAL INSTRUCTION: Return ONLY valid, executable Python code. Do NOT wrap your answer in markdown code blocks like ```python. Do not include any explanations.
    
    Current Code:
    {current_code}
    
    Last Known Error Logs:
    {state['test_result']}
    """
    
    # Call Gemini via our smart retry pipeline
    fixed_code = call_gemini_with_retry(prompt)

    # Physically write the AI's proposed fix into our target application folder
    with open(target_file_path, "w") as f:
        f.write(fixed_code)
    
    print("📝 [Patch Agent]: Written proposed fix to target_app/app.py")
    
    return {
        "proposed_fix": fixed_code,
        "attempt_count": current_attempts,
        "history": state["history"] + [f"Applied fix code version {current_attempts}"]
    }

def validation_agent(state: AgentState) -> Dict:
    print("🧪 [Validation Agent]: Spinning up Docker sandbox to test the application...")
    
    target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
    sandbox_output = run_in_sandbox(target_file_path)
    
    exit_code = sandbox_output["exit_code"]
    logs = sandbox_output["logs"]
    
    if exit_code == 0:
        status = "PASS"
        print("✅ Sandbox execution succeeded! Code is working perfectly.")
    else:
        status = f"FAIL\n{logs}"
        print("❌ Sandbox execution failed with logs.")
        # Add this line right here to display the diagnostic printout:
        print(f"\n📊 [DIAGNOSTIC LOGS CAPTURED]:\n{logs}\n" + "-"*50)
        
    return {
        "test_result": status,
        "history": state["history"] + [f"Tests evaluated with exit code {exit_code}"]
    }

def human_intervention(state: AgentState) -> Dict:
    print("\n🚨 [SYSTEM ALERT]: Agent reached maximum loop attempts without a fix.")
    print("Handing over to human supervisor...")
    return {"history": state["history"] + ["Handed over to human"]}

# 3. Define the Router
def should_continue(state: AgentState) -> str:
    if "PASS" in state["test_result"]:
        return END
    if state["attempt_count"] >= 3:
        return "human_call"
    return "try_again"

# 4. Build the Graph
workflow = StateGraph(AgentState)
workflow.add_node("patcher", patch_agent)
workflow.add_node("validator", validation_agent)
workflow.add_node("human_gate", human_intervention)

workflow.set_entry_point("patcher")
workflow.add_edge("patcher", "validator")
workflow.add_conditional_edges(
    "validator",
    should_continue,
    {
        "try_again": "patcher",
        "human_call": "human_gate",
        END: END
    }
)
workflow.add_edge("human_gate", END)
app = workflow.compile()

if __name__ == "__main__":
    initial_state = {
        "bug_description": "NameError: name 'discount' is not defined",
        "proposed_fix": "",
        "test_result": "Initial run trace required",
        "attempt_count": 0,
        "history": []
    }
    
    print("Starting Fully Powered Project Olympus Agent with Single Key Backoff Engine...")
    app.invoke(initial_state)