#!/usr/bin/env bash
# Push current branch to Hugging Face Spaces (main), removing binary xlsx from history.
# HF rejects binary files; student-version history contains the xlsx, so we push a cleaned branch.
set -e
BRANCH="${1:-student-version}"
REMOTE="${2:-huggingface}"
HF_BRANCH="${3:-hf-push}"

echo "Creating $HF_BRANCH from $BRANCH, stripping data/National_Directory_SU_2024.xlsx from history..."
git checkout -B "$HF_BRANCH" "$BRANCH"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --index-filter 'git rm --cached --ignore-unmatch data/National_Directory_SU_2024.xlsx' --prune-empty HEAD

echo "Pushing $HF_BRANCH to $REMOTE main (force)..."
git push "$REMOTE" "$HF_BRANCH:main" --force

echo "Switching back to $BRANCH and deleting $HF_BRANCH..."
git checkout "$BRANCH"
git branch -D "$HF_BRANCH"

echo "Done. Space updated: https://huggingface.co/spaces/phanny/6.C395-chatbot"
