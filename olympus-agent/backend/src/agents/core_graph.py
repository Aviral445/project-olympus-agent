import sys
import os
import re
from typing import Dict, TypedDict, List
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv, find_dotenv

# Ensure backend directory and src are in sys.path dynamically
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, '../..'))

for p in [SRC_DIR, BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(find_dotenv(), override=True)

from utils.sast_scanner import run_sast_scan
from utils.attestation import sign_patch_attestation
from utils.code_graph import build_repository_map
from utils.telemetry import trace_span
from utils.sandbox import run_in_sandbox 
from utils.git_manager import init_fix_branch, generate_patch_diff, commit_patch

from database.db import init_db
from rag.patch_memory import record_patch_experience, retrieve_similar_experiences
from rag.code_rag import index_codebase_rag, retrieve_relevant_code_context

# Initialize Database & Index Codebase RAG on graph startup
init_db()

# 1. State Definition
class AgentState(TypedDict):
    bug_description: str
    proposed_fix: str
    test_result: str
    attempt_count: int
    target_file: str
    history: List[str]
    last_diff: str

def clean_llm_code_output(raw_code: str) -> str:
    """Strips markdown code blocks from LLM responses."""
    cleaned = raw_code.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned.strip()

def invoke_llm_with_fallback(prompt: str) -> str:
    """Multi-LLM Fallback: Groq -> OpenRouter -> Gemini Direct."""
    groq_key = os.getenv("GROQ_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if groq_key and not groq_key.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via Groq (llama-3.3-70b-versatile)...")
            from langchain_groq import ChatGroq
            llm_groq = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_key, temperature=0.1)
            response = llm_groq.invoke(prompt)
            content = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
            return content.strip()
        except Exception as e:
            print(f"⚠️ [Groq Limit/Error]: {e}\n🔄 [LLM Engine]: Switching to Tier 2 (OpenRouter)...")

    if openrouter_key and not openrouter_key.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via OpenRouter (openrouter/auto)...")
            from langchain_openai import ChatOpenAI
            llm_openrouter = ChatOpenAI(model="openrouter/auto", openai_api_key=openrouter_key, openai_api_base="[https://openrouter.ai/api/v1](https://openrouter.ai/api/v1)", temperature=0.1)
            response = llm_openrouter.invoke(prompt)
            content = response.content if isinstance(response.content, str) else response.content[0].get("text", "")
            return content.strip()
        except Exception as e:
            print(f"⚠️ [OpenRouter Limit/Error]: {e}\n🔄 [LLM Engine]: Switching to Tier 3 (Gemini Direct)...")

    if gemini_key and not gemini_key.startswith("your_"):
        try:
            print("📡 [LLM Engine]: Requesting patch via Gemini Direct (gemini-2.0-flash)...")
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm_gemini = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=gemini_key)
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

    with trace_span("patch_agent", {"attempt": current_attempts}):
        target_file_path = state.get("target_file")
        if not target_file_path or not os.path.exists(target_file_path):
            target_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))

        print(f"\n🤖 [Patch Agent]: Targeting {os.path.basename(target_file_path)} (Attempt #{current_attempts})...")
        
        with open(target_file_path, "r", encoding="utf-8") as f:
            current_code = f.read()

        target_dir = os.path.dirname(target_file_path)
        
        # Re-index target codebase into RAG vector store
        index_codebase_rag(target_dir)

        # 1. RAG Context: Retrieve precise source code & test assertions for this error
        rag_code_context = retrieve_relevant_code_context(state.get("test_result", ""))

        # 2. Memory Context: Retrieve past lesson anti-patterns from ChromaDB
        memory_lessons = retrieve_similar_experiences(state.get("test_result", ""))

        prompt = f"""
        You are an autonomous SRE agent. Fix the target Python file so ALL tests pass simultaneously.
        Return ONLY valid, executable Python code for the target file. Do NOT use markdown formatting like ```python or any explanations.

        {rag_code_context}

        {memory_lessons}

        Target File: {os.path.basename(target_file_path)}
        Code:
        {current_code}

        Failure Output & Error Traceback:
        {state['test_result']}

        INSTRUCTIONS:
        - Inspect the retrieved test assertions and error tracebacks carefully.
        - Pay close attention to boundary condition checks (e.g. return 0 vs raise ValueError).
        - Satisfy all test assertions at once without causing oscillation.
        """
        
        raw_response = invoke_llm_with_fallback(prompt)
        fixed_code = clean_llm_code_output(raw_response)

        # SAST Scan
        sast_res = run_sast_scan(target_file_path)
        if not sast_res["passed"]:
            print(f"🚨 [SAST Gate Rejected]: Security flaws detected!\n{sast_res['logs']}")

        init_fix_branch(f"olympus/patch-attempt-{current_attempts}")

        with open(target_file_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)
        
        diff_summary = generate_patch_diff(target_file_path)
        print(f"\n🔍 [Git Diff Generated]:\n{diff_summary or 'No visible diff changes.'}\n")

        sign_patch_attestation(diff_summary, f"patch-attempt-{current_attempts}")
        commit_patch(target_file_path, current_attempts)
        
        print(f"📝 [Patch Agent]: Applied and committed updates to {target_file_path}")
        
        return {
            "proposed_fix": fixed_code,
            "attempt_count": current_attempts,
            "target_file": target_file_path,
            "last_diff": diff_summary,
            "history": state["history"] + [f"Applied fix v{current_attempts}"]
        }

def validation_agent(state: AgentState) -> Dict:
    current_attempts = state.get("attempt_count", 1)

    with trace_span("validation_agent", {"attempt": current_attempts}):
        target_file_path = state.get("target_file") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
        sandbox_output = run_in_sandbox(target_file_path)
        git_diff = state.get("last_diff", "")

        if sandbox_output["exit_code"] == 0:
            print("\n✅ [Validation Agent]: All tests passed in sandbox!")
            record_patch_experience(
                target_file=os.path.basename(target_file_path),
                attempt=current_attempts,
                status="PASS",
                git_diff=git_diff,
                error_logs=sandbox_output['logs']
            )
            return {
                "test_result": "PASS",
                "history": state["history"] + ["Tests passed."]
            }
        
        logs = sandbox_output["logs"]
        record_patch_experience(
            target_file=os.path.basename(target_file_path),
            attempt=current_attempts,
            status="FAIL",
            git_diff=git_diff,
            error_logs=logs
        )

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
    print("\n" + "="*60)
    print("🚨 [STATUS]: HUMAN INTERVENTION REQUIRED")
    print("="*60)
    print(f"📌 Target File : {os.path.basename(state.get('target_file', ''))}")
    print(f"🔄 Total Attempts: {state.get('attempt_count')}")
    print(f"❌ Unresolved Error:\n{state.get('test_result')}")
    print("="*60 + "\n")
    return {"history": state["history"] + ["Handed over to human"]}

def should_continue(state: AgentState) -> str:
    if "PASS" in state["test_result"]:
        return END
    if state["attempt_count"] >= 5:
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
        "last_diff": "",
        "history": []
    }
    
    print("🚀 Starting Project Olympus Execution Pipeline with Tree-sitter RAG & Memory...")
    final_state = app.invoke(initial_state)
    
    if "PASS" in final_state.get("test_result", ""):
        print("\n" + "="*60)
        print("🎉 [STATUS]: SUCCESS - AUTOMATICALLY PATCHED & VERIFIED!")
        print("="*60)
        print(f"📌 Target File : {os.path.basename(final_state.get('target_file', ''))}")
        print(f"🔄 Attempts Taken: {final_state.get('attempt_count')}")
        print("\n🔍 [SUMMARY OF CHANGES (GIT DIFF)]:")
        print(final_state.get("last_diff") or "No visible diff.")
        print("="*60 + "\n")