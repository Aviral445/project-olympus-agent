import sys
import os
from pathlib import Path

# Add backend directory to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import chromadb
import tree_sitter_language_pack as tslp

# Store ChromaDB codebase index in backend/rag/data/vector_db
DATA_DIR = CURRENT_DIR / "data" / "vector_db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=str(DATA_DIR))
code_collection = chroma_client.get_or_create_collection(name="codebase_chunks")

def chunk_file_with_treesitter(file_path: str) -> list:
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    chunks = []
    lines = content.splitlines()
    
    try:
        parsed = tslp.process(content, "python")
        structure = parsed.get("structure", [])

        if not structure:
            return [{"id": os.path.basename(file_path), "content": content, "file": file_path}]

        for sym in structure:
            sym_name = sym.get("name", "block")
            start_line = max(0, sym.get("line", 1) - 1)
            end_line = min(len(lines), start_line + 35)
            chunk_code = "\n".join(lines[start_line:end_line])

            chunks.append({
                "id": f"{os.path.basename(file_path)}::{sym_name}",
                "symbol": sym_name,
                "file": file_path,
                "content": f"# File: {os.path.basename(file_path)} | Symbol: {sym_name}\n{chunk_code}"
            })

    except Exception as e:
        print(f"⚠️ [Tree-sitter Chunking Warning]: {e}")
        chunks.append({"id": os.path.basename(file_path), "content": content, "file": file_path})

    return chunks

def index_codebase_rag(target_dir: str):
    clean_dir = Path(target_dir).resolve()
    if not clean_dir.exists():
        print(f"Directory not found: {target_dir}")
        return

    documents = []
    metadatas = []
    ids = []

    for root, _, files in os.walk(clean_dir):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                file_chunks = chunk_file_with_treesitter(full_path)

                for chunk in file_chunks:
                    documents.append(chunk["content"])
                    metadatas.append({"file": os.path.basename(full_path), "symbol": chunk.get("symbol", "file")})
                    ids.append(chunk["id"])

    if documents:
        try:
            code_collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"🌲 [Tree-sitter RAG]: Indexed {len(documents)} AST chunks across codebase into ChromaDB.")
        except Exception as e:
            print(f"⚠️ [Tree-sitter RAG Indexing Error]: {e}")

def retrieve_relevant_code_context(error_log: str, top_k: int = 3) -> str:
    if not error_log or code_collection.count() == 0:
        return ""

    try:
        results = code_collection.query(
            query_texts=[error_log],
            n_results=min(top_k, code_collection.count())
        )

        documents = results.get("documents", [[]])[0]
        if not documents:
            return ""

        context_blocks = ["\n🎯 [Codebase RAG - Relevant Code & Test Assertions]:"]
        for doc in documents:
            context_blocks.append(f"---\n{doc}")

        return "\n".join(context_blocks) + "\n"

    except Exception as e:
        print(f"⚠️ [RAG Context Retrieval Error]: {e}")
        return ""

if __name__ == "__main__":
    print("Testing Tree-sitter Codebase RAG...")
    sample_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../target_app"))
    index_codebase_rag(sample_dir)
    
    query = "FAILED tests/test_calculator.py::test_negative_values - ValueError: Price cannot be negative"
    retrieved = retrieve_relevant_code_context(query)
    print("\nRetrieved Context:\n", retrieved)