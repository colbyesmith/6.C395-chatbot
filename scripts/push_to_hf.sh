#!/usr/bin/env bash
# Push student-version to Hugging Face Space (updates main on the Space).
# Binary xlsx was removed from history, so a normal push works.
set -e
git push huggingface student-version:main
echo "Done. https://huggingface.co/spaces/phanny/6.C395-chatbot"
