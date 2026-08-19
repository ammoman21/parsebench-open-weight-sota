#!/bin/bash
# Run after `hf auth login` (or huggingface-cli login) with a WRITE token.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=parsebench/.venv/bin/python
$PY - <<'PYEOF'
from huggingface_hub import HfApi
api = HfApi()
repo = "florin-inc/florin-parser-nano"
api.create_repo(repo, private=True, exist_ok=True)
api.upload_folder(folder_path="it7_merged", repo_id=repo)
api.upload_folder(folder_path="it7_adapter", repo_id=repo, path_in_repo="adapter")
api.upload_file(path_or_fileobj="publish/MODEL_CARD.md", path_in_repo="README.md", repo_id=repo)
api.upload_file(path_or_fileobj="publish/parsebench.yaml", path_in_repo=".eval_results/parsebench.yaml", repo_id=repo)
print("uploaded (PRIVATE):", f"https://huggingface.co/{repo}")
PYEOF
