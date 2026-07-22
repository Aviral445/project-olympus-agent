import os
from pathlib import Path
import tree_sitter_language_pack as tslp

def extract_symbols_from_ast(code_bytes: bytes, language: str = "python") -> list:
    """
    Parses code using Tree-sitter and traverses the Abstract Syntax Tree (AST) 
    node-by-node to extract function/method signatures, class definitions, and line numbers.
    """
    try:
        parser = tslp.get_parser(language)
        tree = parser.parse(code_bytes)
        root_node = tree.root_node

        symbols = []

        def walk_node(node):
            if node.type in ("function_definition", "async_function_definition"):
                name_node = node.child_by_field_name("name")
                params_node = node.child_by_field_name("parameters")
                
                func_name = name_node.text.decode("utf-8") if name_node else "unknown"
                params = params_node.text.decode("utf-8") if params_node else "()"
                line_no = node.start_point[0] + 1
                
                symbols.append({
                    "type": "function",
                    "name": func_name,
                    "signature": params,
                    "line": line_no
                })

            elif node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                class_name = name_node.text.decode("utf-8") if name_node else "unknown"
                line_no = node.start_point[0] + 1
                
                symbols.append({
                    "type": "class",
                    "name": class_name,
                    "line": line_no
                })

            # Recursively walk child nodes
            for child in node.children:
                walk_node(child)

        walk_node(root_node)
        return symbols

    except Exception as e:
        return [{"type": "error", "message": f"Tree-sitter parse failed: {str(e)}"}]

def build_compact_repo_map(target_dir: str = "backend/target_app") -> str:
    """
    Scans a directory using Tree-sitter AST parsing to build a 
    token-optimized repository map showing function signatures,
    classes, and line numbers across all files.
    """
    clean_dir = Path(target_dir).resolve()
    if not clean_dir.exists():
        return f"Directory not found: {target_dir}"

    repo_map_lines = ["=== REPOSITORY MAP (Tree-sitter AST) ==="]

    for root, _, files in os.walk(clean_dir):
        for file in files:
            if file.endswith(".py"):
                full_path = Path(root) / file
                rel_path = full_path.relative_to(clean_dir).as_posix()
                
                try:
                    with open(full_path, "rb") as f:
                        code_bytes = f.read()
                    
                    symbols = extract_symbols_from_ast(code_bytes, language="python")
                    
                    if symbols:
                        repo_map_lines.append(f"\n📄 {rel_path}:")
                        for sym in symbols:
                            sym_type = sym.get("type")
                            name = sym.get("name", "unknown")
                            line = sym.get("line", 0)
                            
                            if sym_type == "function":
                                sig = sym.get("signature", "()")
                                repo_map_lines.append(f"  │-- def {name}{sig} (Line {line})")
                            elif sym_type == "class":
                                repo_map_lines.append(f"  └── class {name} (Line {line})")
                            elif sym_type == "error":
                                repo_map_lines.append(f"  ⚠️ {sym.get('message')}")
                except Exception as e:
                    repo_map_lines.append(f"  ⚠️ Error reading {rel_path}: {e}")

    return "\n".join(repo_map_lines)

if __name__ == "__main__":
    # Test Tree-sitter Repo Mapper against target_app
    sample_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app"))
    print("Testing Tree-sitter Repo Mapper...")
    repo_map = build_compact_repo_map(sample_dir)
    print("\nGenerated Compact Repo Map:\n")
    print(repo_map)