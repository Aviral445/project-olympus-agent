import sys
import os
import re
from typing import Dict, TypedDict, List
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

# Configure paths and load environment variables
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env')))

from utils.sandbox import run_in_sandbox 
from utils.git_manager import init_fix_branch, generate_patch_diff, commit_patch

# 1. State Definition
class AgentState(TypedDict):
    bug_description: str
    proposed_fix: str
    test_result: str
    attempt_count: int
    target_file: str
    history: List[str]

GROQ_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def clean_llm_code_output(raw_code: str) -> str:
    """Strips markdown code blocks from LLM responses."""
    cleaned = raw_code.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned.strip()

def invoke_llm_with_fallback(prompt: str) -> str:
    """
    Tier 1: Groq (llama-3.3-70b-versatile) - Blazing speed
    Tier 2: OpenRouter (openrouter/auto or google/gemini-2.0-flash-001)
    Tier 3: Gemini Direct (gemini-2.0-flash)
    """
    # --- TIER 1: GROQ ---
    if GROQ_KEY and not GROQ_KEY.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via Groq (llama-3.3-70b-versatile)...")
            llm_groq = ChatGroq(
                model="llama-3.3-70b-versatile",
                groq_api_key=GROQ_KEY,
                temperature=0.1
            )
            response = llm_groq.invoke(prompt)
            content = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
            return content.strip()
        except Exception as e:
            print(f"⚠️ [Groq Limit/Error]: {e}")
            print("🔄 [LLM Engine]: Switching to Tier 2 (OpenRouter)...")

    # --- TIER 2: OPENROUTER ---
    if OPENROUTER_KEY and not OPENROUTER_KEY.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via OpenRouter (openrouter/auto)...")
            llm_openrouter = ChatOpenAI(
                model="openrouter/auto",
                openai_api_key=OPENROUTER_KEY,
                openai_api_base="[https://openrouter.ai/api/v1](https://openrouter.ai/api/v1)",
                temperature=0.1
            )
            response = llm_openrouter.invoke(prompt)
            content = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
            return content.strip()
        except Exception as e:
            print(f"⚠️ [OpenRouter Limit/Error]: {e}")
            print("🔄 [LLM Engine]: Switching to Tier 3 (Gemini Direct)...")

    # --- TIER 3: GEMINI DIRECT ---
    if GEMINI_KEY and not GEMINI_KEY.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via Gemini Direct (gemini-2.0-flash)...")
            llm_gemini = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=GEMINI_KEY
            )
            response = llm_gemini.invoke(prompt)
            content = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
            return content.strip()
        except Exception as e:
            print(f"❌ [Gemini Direct Error]: {e}")
            raise e

    raise RuntimeError("No operational LLM key found across Groq, OpenRouter, or Gemini.")

# 2. Agent Nodes
def patch_agent(state: AgentState) -> Dict:
    current_attempts = state.get("attempt_count", 0) + 1
    
    target_file_path = state.get("target_file")
    if not target_file_path or not os.path.exists(target_file_path):
        target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))

    print(f"\n🤖 [Patch Agent]: Targeting {os.path.basename(target_file_path)} (Attempt #{current_attempts})...")
    
    with open(target_file_path, "r", encoding="utf-8") as f:
        current_code = f.read()

    prompt = f"""
    You are an autonomous SRE agent. Fix the following broken Python code.
    Return ONLY valid, executable Python code. Do NOT use markdown formatting like ```python or any explanations.
    
    File: {os.path.basename(target_file_path)}
    Code:
    {current_code}
    
    Error Logs:
    {state['test_result']}
    """
    
    raw_response = invoke_llm_with_fallback(prompt)
    fixed_code = clean_llm_code_output(raw_response)

    # 1. Switch or create fix branch
    init_fix_branch(f"olympus/patch-attempt-{current_attempts}")

    # 2. Apply code updates to target file
    with open(target_file_path, "w", encoding="utf-8") as f:
        f.write(fixed_code)
    
    # 3. Generate git diff for logs
    diff_summary = generate_patch_diff(target_file_path)
    print(f"\n🔍 [Git Diff Generated]:\n{diff_summary or 'No visible diff changes.'}\n")

    # 4. Commit changes locally
    commit_patch(target_file_path, current_attempts)
    
    print(f"📝 [Patch Agent]: Applied and committed updates to {target_file_path}")
    
    return {
        "proposed_fix": fixed_code,
        "attempt_count": current_attempts,
        "target_file": target_file_path,
        "history": state["history"] + [f"Applied fix v{current_attempts}"]
    }

def validation_agent(state: AgentState) -> Dict:
    print("🧪 [Validation Agent]: Spinning up Docker sandbox to test application...")
    
    target_file_path = state.get("target_file") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
    sandbox_output = run_in_sandbox(target_file_path)
    
    if sandbox_output["exit_code"] == 0:
        print("\n✅ [Validation Agent]: All tests passed in sandbox!")
        print(f"📊 [LOGS]:\n{sandbox_output['logs']}\n" + "-"*40)
        return {
            "test_result": "PASS",
            "history": state["history"] + ["Tests passed."]
        }
    
    logs = sandbox_output["logs"]
    print(f"❌ Sandbox execution failed with logs:\n{logs}\n" + "-"*40)
    
    # Traceback file isolation
    discovered_file = target_file_path
    matches = re.findall(r'([\w-]+\.py):\d+', logs)
    if matches:
        for filename in matches:
            if "test_" not in filename:
                potential_path = os.path.join(os.path.dirname(target_file_path), filename)
                if os.path.exists(potential_path):
                    discovered_file = os.path.abspath(potential_path)
                    print(f"🎯 [ENGINE NOTE]: Dynamically isolated root cause inside: {filename}")
                    break

    return {
        "test_result": f"FAIL\n{logs}",
        "target_file": discovered_file,
        "history": state["history"] + [f"Failed. Target file set to: {os.path.basename(discovered_file)}"]
    }

def human_intervention(state: AgentState) -> Dict:
    print("\n🚨 [SYSTEM ALERT]: Maximum attempts reached without a clean pass.")
    print("Passing control to human operator...")
    return {"history": state["history"] + ["Handed over to human"]}

def should_continue(state: AgentState) -> str:
    if "PASS" in state["test_result"]:
        return END
    if state["attempt_count"] >= 3:
        return "human_call"
    return "try_again"

# 3. Graph Assembly
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
        "bug_description": "Initial bug trace",
        "proposed_fix": "",
        "test_result": "Initial run required",
        "attempt_count": 0,
        "target_file": "",
        "history": []
    }
    
    print("Starting Project Olympus: Multi-File Discovery Framework...")
    app.invoke(initial_state)