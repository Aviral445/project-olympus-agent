import docker
import os

def run_in_sandbox(script_path: str) -> dict:
    """
    Spins up a secure, isolated Python container, runs the target script,
    and returns the exit code and error logs.
    """
    # Initialize the Docker client from your local system
    client = docker.from_env()
    
    # Get the absolute path to the directory containing our broken app
    absolute_app_dir = os.path.abspath(os.path.dirname(script_path))
    script_name = os.path.basename(script_path)
    
    print(f"📦 Mount directory: {absolute_app_dir}")
    print(f"🧪 Running script: {script_name} inside container...")

    try:
        # === UPDATED FOR WINDOWS COMPATIBILITY ===
        container = client.containers.run(
            image="python:3.11-slim",
            command="python /app/app.py", 
            volumes={
                absolute_app_dir: {
                    'bind': '/app',
                    'mode': 'ro' 
                }
            },
            network_mode="none", 
            detach=True
        )
        # =========================================
        
        # Wait for the container to finish executing the code
        result = container.wait()
        exit_code = result["StatusCode"]
        
        # Fetch the console output (stdout and stderr combined)
        logs = container.logs().decode("utf-8")
        
        # Clean up the container so we don't leave trash behind
        container.remove()
        
        return {
            "exit_code": exit_code,
            "logs": logs
        }
        
    except Exception as e:
        return {
            "exit_code": -1,
            "logs": f"Sandbox Execution Failed: {str(e)}"
        }

# --- TEST THE SANDBOX ---
if __name__ == "__main__":
    target = "./target_app/app.py"
    output = run_in_sandbox(target)
    
    print("\n--- SANDBOX RESULTS ---")
    print(f"Exit Code: {output['exit_code']} (0 means success, anything else means failure)")
    print("Container Output logs:")
    print(output['logs'])