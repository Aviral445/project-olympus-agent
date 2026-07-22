import os
import ast
from pathlib import Path

def parse_file_structure(file_path: str) -> dict:
    """
    Parses a single Python file into an Abstract Syntax Tree (AST) 
    and extracts all class and function signatures.
    """
    clean_path = Path(file_path).as_posix()
    if not os.path.exists(clean_path):
        return {"error": f"File not found: {clean_path}"}

    try:
        with open(clean_path, "r", encoding="utf-8") as f:
            code_content = f.read()

        tree = ast.parse(code_content)

        functions = []
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Get function name and argument list
                args = [arg.arg for arg in node.args.args]
                functions.append({"name": node.name, "args": args, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                classes.append({"name": node.name, "line": node.lineno})

        return {
            "file": os.path.basename(clean_path),
            "functions": functions,
            "classes": classes
        }
    except Exception as e:
        return {"file": os.path.basename(clean_path), "error": str(e)}

def build_repository_map(target_dir: str = "backend/target_app") -> list:
    """
    Scans a directory and builds an AST symbol map of all Python files.
    """
    repo_map = []
    clean_dir = Path(target_dir).as_posix()

    if not os.path.exists(clean_dir):
        return repo_map

    print(f"🌳 [Code Graph]: Building AST Symbol Map for directory '{target_dir}'...")

    for root, _, files in os.walk(clean_dir):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                parsed = parse_file_structure(full_path)
                repo_map.append(parsed)

    return repo_map

if __name__ == "__main__":
    # Test AST parsing against target_app
    sample_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app"))
    result = build_repository_map(sample_dir)
    print("AST Symbol Graph:", result)