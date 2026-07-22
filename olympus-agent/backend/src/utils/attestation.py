import os
import subprocess
from pathlib import Path

def sign_patch_attestation(diff_content: str, patch_id: str = "patch") -> dict:
    """
    Saves a Git diff to a temporary attestation artifact and cryptographically 
    signs it using Sigstore keyless infrastructure.
    """
    if not diff_content or not diff_content.strip():
        return {"signed": False, "message": "Empty diff content. Skipping signing."}

    # Ensure output directory exists
    artifact_dir = Path("backend/artifacts").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    diff_file = artifact_dir / f"{patch_id}.diff"
    
    # Save the diff payload
    with open(diff_file, "w", encoding="utf-8") as f:
        f.write(diff_content)

    print(f"✍️ [Sigstore Attestation]: Signing artifact '{diff_file.name}'...")

    try:
        # In automated CI/CD (e.g. GitHub Actions), Sigstore uses ambient OIDC tokens automatically.
        # Locally, we run in identity-token verification / staging mode.
        cmd = [
            "sigstore", "sign",
            "--oauth-identity-token", "offline",
            str(diff_file)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode == 0:
            print(f"✅ [Sigstore Attestation]: Successfully generated signature bundle for {patch_id}!")
            return {
                "signed": True,
                "artifact_path": str(diff_file),
                "bundle_path": f"{str(diff_file)}.sigstore.json"
            }
        else:
            # Local fallback mode when interactive browser auth is omitted
            print("ℹ️ [Sigstore Attestation]: Local identity token required for full PKI verification. Skipping online bundle publish.")
            return {
                "signed": False,
                "artifact_path": str(diff_file),
                "message": "Local unsigned snapshot logged to artifacts directory."
            }

    except Exception as e:
        print(f"⚠️ [Sigstore Attestation]: Signing skipped ({str(e)})")
        return {
            "signed": False,
            "artifact_path": str(diff_file),
            "message": str(e)
        }

if __name__ == "__main__":
    # Test signing logic with a sample diff
    sample_diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-return price - discount\n+return max(0, price - discount)"
    res = sign_patch_attestation(sample_diff, "sample_patch_1")
    print("Attestation Result:", res)