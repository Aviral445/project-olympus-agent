import sys
import os
import time
import re
from typing import Dict, TypedDict, List
from unittest import result
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Configure paths and load environment variables
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env')))

from utils.sandbox import run_in_sandbox 

# 1. Define the Expanded Global State
class AgentState(TypedDict):
    bug_description: str
    proposed_fix: str
    test_result: str
    attempt_count: int
    target_file: str  # Dynamic target path discovered by the agent
    history: List[str]

API_KEY = os.getenv("GEMINI_API_KEY")

def call_gemini_with_retry(prompt: str, max_retries: int = 4, initial_delay: int = 5) -> str:
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
            # Catch quota depletion or generic server busy indicators
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "503" in error_msg:
                if attempt < max_retries - 1:
                    # If it's a harsh daily limit quota wall, wait out a solid window
                    wait_time = 65 if "RESOURCE_EXHAUSTED" in error_msg else delay
                    print(f"\n⚠️ [Rate Limit / Quota Hit]: Sleeping for {wait_time}s to clear API window (Attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    delay *= 2
                    continue
            raise e

# 2. Define the Nodes
def patch_agent(state: AgentState) -> Dict:
    current_attempts = state.get("attempt_count", 0) + 1
    
    # Use the dynamically discovered file, or default if it's the first run
    target_file_path = state.get("target_file")
    if not target_file_path or not os.path.exists(target_file_path):
        target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))

    print(f"\n🤖 [Patch Agent]: Targeting file: {os.path.basename(target_file_path)} (Attempt #{current_attempts})...")
    
    with open(target_file_path, "r") as f:
        current_code = f.read()

    prompt = f"""
    You are an autonomous SRE agent. Your goal is to fix the following broken Python code.
    
    CRITICAL INSTRUCTION: Return ONLY valid, executable Python code. Do NOT wrap your answer in markdown code blocks like ```python. Do not include any explanations.
    
    Current Code from {os.path.basename(target_file_path)}:
    {current_code}
    
    Last Known Error Logs:
    {state['test_result']}
    """
    
    fixed_code = call_gemini_with_retry(prompt)

    with open(target_file_path, "w") as f:
        f.write(fixed_code)
    
    print(f"📝 [Patch Agent]: Applied updates to {target_file_path}")
    
    return {
        "proposed_fix": fixed_code,
        "attempt_count": current_attempts,
        "target_file": target_file_path,
        "history": state["history"] + [f"Applied fix to {os.path.basename(target_file_path)} v{current_attempts}"]
    }

def validation_agent(state: AgentState) -> Dict:
    print("🧪 [Validation Agent]: Spinning up Docker sandbox to test the application...")
    
    target_file_path = state.get("target_file")
    if not target_file_path:
        target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
        
    sandbox_output = run_in_sandbox(target_file_path)
    exit_code = sandbox_output["exit_code"]
    logs = sandbox_output["logs"]
    
    if exit_code == 0:
        print("\n✅ [Validation Agent]: All tests passed in the sandbox!")
        print(f"📊 [TEST LOGS]:\n{logs}\n" + "-"*50)
        return {
            "test_result": "PASS",
            "history": state["history"] + ["Tests passed successfully."]
        }
    
    print("❌ Sandbox execution failed with logs.")
    print(f"\n📊 [DIAGNOSTIC LOGS CAPTURED]:\n{logs}\n" + "-"*50)
    
    # Trace logic for broken files
    discovered_file = target_file_path
    matches = re.findall(r'([\w-]+\.py):\d+', logs)
    if matches:
        for filename in matches:
            if "test_" not in filename:
                base_dir = os.path.dirname(target_file_path)
                potential_path = os.path.join(base_dir, filename)
                if os.path.exists(potential_path):
                    discovered_file = os.path.abspath(potential_path)
                    print(f"🎯 [ENGINE NOTE]: Dynamically isolated root cause inside: {filename}")
                    break

    return {
        "test_result": f"FAIL\n{logs}",
        "target_file": discovered_file,
        "history": state["history"] + [f"Tests failed. Target file set to: {os.path.basename(discovered_file)}"]
    }

def human_intervention(state: AgentState) -> Dict:
    print("\n🚨 [SYSTEM ALERT]: Agent reached maximum loop attempts without a fix.")
    print("Handing over to human supervisor...")
    return {"history": state["history"] + ["Handed over to human"]}

def should_continue(state: AgentState) -> str:
    if "PASS" in state["test_result"]:
        return END
    if state["attempt_count"] >= 3:
        return "human_call"
    return "try_again"

workflow = StateGraph(AgentState)
workflow.add_node("patcher", patch_agent)
workflow.add_node("validator", validation_agent)
workflow.add_node("human_gate", human_intervention)

workflow.set_entry_point("patcher")
workflow.add_edge("patcher", "validator")
workflow.add_conditional_edges(
    "validator",
    should_continue,
    {"try_again": "patcher", "human_call": "human_gate", END: END}
)
workflow.add_edge("human_gate", END)
app = workflow.compile()

if __name__ == "__main__":
    initial_state = {
        "bug_description": "NameError: name 'discount' is not defined",
        "proposed_fix": "",
        "test_result": "Initial run trace required",
        "attempt_count": 0,
        "target_file": "",
        "history": []
    }
    
    print("Starting Project Olympus: Multi-File Discovery Framework...")
    app.invoke(initial_state)