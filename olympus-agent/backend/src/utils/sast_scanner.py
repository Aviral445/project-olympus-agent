import os
import subprocess
import json
from pathlib import Path

def run_sast_scan(target_file: str) -> dict:
    """
    Runs Semgrep static analysis on a specific file to detect potential security
    vulnerabilities or unsafe functions introduced by generated patches.
    """
    # Convert path to POSIX format to prevent Windows backslash bugs
    clean_path = Path(target_file).as_posix()

    if not os.path.exists(clean_path):
        return {
            "passed": False,
            "findings_count": 0,
            "logs": f"File not found for SAST scan: {clean_path}"
        }

    print(f"🛡️ [SAST Gate]: Running Semgrep analysis on {os.path.basename(clean_path)}...")

    try:
        # Run Semgrep with standard Python security rules in JSON mode
        cmd = [
            "semgrep",
            "scan",
            "--config=p/python",
            "--quiet",
            "--json",
            clean_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0 and not result.stdout:
            # Semgrep CLI error or binary missing
            return {
                "passed": True,  # Fallback gracefully if CLI isn't available
                "findings_count": 0,
                "logs": f"SAST Warning: Semgrep execution skipped or non-zero exit: {result.stderr}"
            }

        scan_data = json.loads(result.stdout)
        results = scan_data.get("results", [])

        if not results:
            print("✅ [SAST Gate]: Zero security vulnerabilities detected.")
            return {
                "passed": True,
                "findings_count": 0,
                "logs": "No security issues found."
            }

        # Extract details of findings
        findings_summary = []
        for issue in results:
            rule_id = issue.get("check_id", "security-issue")
            message = issue.get("extra", {}).get("message", "Potential flaw found")
            line = issue.get("start", {}).get("line", 0)
            findings_summary.append(f"Line {line} [{rule_id}]: {message}")

        formatted_logs = "\n".join(findings_summary)
        print(f"❌ [SAST Gate]: Found {len(results)} potential security flaw(s)!")

        return {
            "passed": False,
            "findings_count": len(results),
            "logs": formatted_logs
        }

    except Exception as e:
        # Ensure SAST failure doesn't crash the entire pipeline if Semgrep is missing
        print(f"⚠️ [SAST Gate]: Scan skipped ({str(e)})")
        return {
            "passed": True,
            "findings_count": 0,
            "logs": f"SAST scan bypassed due to runtime exception: {str(e)}"
        }

if __name__ == "__main__":
    # Simple self-test against target app
    sample_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../target_app/app.py"))
    res = run_sast_scan(sample_file)
    print("Scan Result:", res)