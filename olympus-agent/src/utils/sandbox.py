import docker
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
    Spins up an isolated Docker container, executes pytest, and guarantees
    full extraction of test failure logs from stdout and stderr combined.
    """
    client = docker.from_env()
    
    try:
        root_dir = find_project_root(os.path.dirname(target_file_path))
        target_dir = os.path.join(root_dir, "target_app")
    except Exception as e:
        return {"exit_code": -1, "logs": f"Path Discovery Error: {str(e)}"}
    
    # Force python to output streams unbuffered and run pytest explicitly
    command_str = "python -m pip install pytest; python -m pytest tests/ --tb=short"
    
    try:
        container_output = client.containers.run(
            image="python:3.11-slim",
            command=f"sh -c '{command_str}'",
            volumes={
                target_dir: {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            },
            working_dir="/workspace",
            network_mode="bridge",
            environment={"PYTHONUNBUFFERED": "1"}, # Force immediate log flushing
            detach=False,
            stdout=True,
            stderr=True
        )
        
        return {
            "exit_code": 0,
            "logs": container_output.decode('utf-8')
        }
        
    except docker.errors.ContainerError as e:
        # Retrieve all historical logs directly from the physical container instance
        raw_logs = e.container.logs(stdout=True, stderr=True).decode('utf-8')
        
        # Clean up the container from Docker's memory
        try:
            e.container.remove()
        except:
            pass
            
        return {
            "exit_code": e.exit_status,
            "logs": raw_logs if raw_logs.strip() else "Test failed but no logs were written to stdout/stderr."
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "logs": f"Sandbox System Error: {str(e)}"
        }