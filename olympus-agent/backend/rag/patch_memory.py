import sys
import os
from pathlib import Path

# Add project root (olympus-agent) to sys.path dynamically
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from database.db import log_patch_run

# Store vector database inside backend/rag/data/vector_db
DATA_DIR = CURRENT_DIR / "data" / "vector_db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=str(DATA_DIR))
memory_collection = chroma_client.get_or_create_collection(name="patch_experience")

def record_patch_experience(target_file: str, attempt: int, status: str, git_diff: str, error_logs: str):
    """
    Saves patch execution data to SQLite database and indexes 
    error tracebacks into ChromaDB for semantic retrieval.
    """
    # 1. Save to SQLite
    log_patch_run(
        target_file=target_file,
        attempt=attempt,
        status=status,
        git_diff=git_diff,
        error_logs=error_logs
    )

    # 2. Vector Index Error Traceback if failure occurs
    if status == "FAIL" and error_logs:
        doc_id = f"{target_file}_attempt_{attempt}_{hash(error_logs) & 0xFFFFFFFF}"
        metadata = {
            "target_file": target_file,
            "attempt": attempt,
            "status": status,
            "diff_summary": git_diff[:300]
        }
        
        try:
            memory_collection.add(
                documents=[error_logs],
                metadatas=[metadata],
                ids=[doc_id]
            )
            print(f"🧠 [Memory Engine]: Indexed failure traceback into Knowledge Base (ID: {doc_id})")
        except Exception as e:
            print(f"⚠️ [Memory Engine]: Vector store add warning: {e}")

def retrieve_similar_experiences(current_error_log: str, top_k: int = 2) -> str:
    """
    Queries ChromaDB for past error tracebacks similar to current failure.
    """
    if not current_error_log or memory_collection.count() == 0:
        return ""

    try:
        results = memory_collection.query(
            query_texts=[current_error_log],
            n_results=min(top_k, memory_collection.count())
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return ""

        memory_context = ["\n🧠 [Self-Healing Knowledge Base - Past Relevant Lessons]:"]
        for idx, (doc, meta) in enumerate(zip(documents, metadatas), 1):
            target = meta.get("target_file", "unknown")
            diff = meta.get("diff_summary", "no diff recorded")
            memory_context.append(f"  Lesson #{idx} (Target: {target}):")
            memory_context.append(f"    - Failed Patch Attempt Diff:\n{diff}")
            memory_context.append("    - Rule: Do NOT repeat this patch pattern as it leads to oscillation.")

        return "\n".join(memory_context) + "\n"

    except Exception as e:
        print(f"⚠️ [Memory Engine]: Retrieval warning: {e}")
        return ""

if __name__ == "__main__":
    print("Testing Updated RAG Memory Module...")
    record_patch_experience("app.py", 999, "FAIL", "diff --git a/app.py", "ValueError: Price must be greater than or equal to zero")
    retrieved = retrieve_similar_experiences("ValueError: Price must be greater than or equal to zero")
    print(retrieved)