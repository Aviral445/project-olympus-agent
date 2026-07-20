import subprocess
import os

def find_project_root(current_path: str, anchor: str = ".env") -> str:
    dirname = os.path.abspath(current_path)
    while True:
        if os.path.exists(os.path.join(dirname, anchor)):
            return dirname
        parent = os.path.dirname(dirname)
        if parent == dirname:
            raise FileNotFoundError(f"Could not locate project root containing '{anchor}' anchor.")
        dirname = parent

def run_in_sandbox(target_file_path: str) -> dict:
    """
    Executes pytest inside the olympus-sandbox Docker container using native CLI subprocess calls
    to prevent silent process termination on Windows.
    """
    try:
        root_dir = find_project_root(os.path.dirname(target_file_path))
        target_dir = os.path.join(root_dir, "target_app")
    except Exception as e:
        return {"exit_code": -1, "logs": f"Path Discovery Error: {str(e)}"}

    # Convert Windows path to a format Docker CLI understands cleanly
    clean_target_dir = target_dir.replace("\\", "/")

    # Build native Docker CLI execution command
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{clean_target_dir}:/workspace",
        "-w", "/workspace",
        "-e", "PYTHONUNBUFFERED=1",
        "olympus-sandbox",
        "pytest", "tests/", "--tb=short"
    ]

    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        combined_logs = (result.stdout + "\n" + result.stderr).strip()

        return {
            "exit_code": result.returncode,
            "logs": combined_logs if combined_logs else "No logs recorded from container."
        }

    except Exception as e:
        return {
            "exit_code": -1,
            "logs": f"Subprocess Execution Error: {str(e)}"
        }