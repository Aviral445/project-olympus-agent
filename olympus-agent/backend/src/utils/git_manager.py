import subprocess
import os

def run_git_cmd(args, cwd=None):
    """Executes a git command safely and returns the output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Git Command Error ({' '.join(args)}): {e.stderr.strip()}")
        return ""

def init_fix_branch(branch_name="olympus/auto-fix"):
    """Ensures working directory is clean and checks out a new fix branch."""
    current_branch = run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"])
    
    # Create or checkout the fix branch
    run_git_cmd(["checkout", "-B", branch_name])
    print(f"🌿 [Git Manager]: Switched to branch '{branch_name}' (Base: {current_branch})")
    return branch_name

def generate_patch_diff(target_file):
    """Generates a clean git diff for the modified file."""
    diff_output = run_git_cmd(["diff", target_file])
    if not diff_output:
        # If staged or untracked
        diff_output = run_git_cmd(["diff", "--staged", target_file])
    return diff_output

def commit_patch(target_file, attempt_num):
    """Stages and commits the patch locally."""
    run_git_cmd(["add", target_file])
    msg = f"fix(olympus): autonomous patch attempt #{attempt_num} for {os.path.basename(target_file)}"
    run_git_cmd(["commit", "-m", msg])
    print(f"📦 [Git Manager]: Committed patch #{attempt_num} locally.")