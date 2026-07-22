import hmac
import hashlib
import os
from typing import Dict, Any, Tuple

def verify_github_signature(payload_body: bytes, secret: str, signature_header: str) -> bool:
    """
    Verifies that the incoming webhook request genuinely originated from GitHub
    using the configured WEBHOOK_SECRET.
    """
    if not signature_header or not secret:
        return False

    sha_name, signature = signature_header.split('=') if '=' in signature_header else ('', '')
    if sha_name != 'sha256':
        return False

    mac = hmac.new(secret.encode('utf-8'), msg=payload_body, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

def parse_github_event(event_type: str, payload: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Extracts the bug description, target file, and repository URL 
    from common GitHub webhook events (workflow_run, issues, push).
    """
    bug_description = "GitHub Webhook Triggered Repair"
    target_file = ""
    repo_url = payload.get("repository", {}).get("clone_url", "")

    # Event 1: Failed GitHub Actions CI/CD Workflow Run
    if event_type == "workflow_run":
        action = payload.get("action")
        conclusion = payload.get("workflow_run", {}).get("conclusion")
        if conclusion == "failure":
            workflow_name = payload.get("workflow", {}).get("name", "CI Pipeline")
            commit_msg = payload.get("workflow_run", {}).get("head_commit", {}).get("message", "Recent Commit")
            bug_description = f"GitHub Action '{workflow_name}' failed on commit: '{commit_msg}'"

    # Event 2: New GitHub Issue Opened
    elif event_type == "issues":
        action = payload.get("action")
        if action in ["opened", "reopened"]:
            issue_title = payload.get("issue", {}).get("title", "")
            issue_body = payload.get("issue", {}).get("body", "")
            bug_description = f"Issue #{payload.get('issue', {}).get('number')}: {issue_title}\n\nDetails:\n{issue_body}"

    # Event 3: Commit Push Event
    elif event_type == "push":
        commits = payload.get("commits", [])
        if commits:
            latest_commit = commits[-1]
            bug_description = f"Push Event Commit: {latest_commit.get('message', '')}"

    return bug_description, target_file, repo_url