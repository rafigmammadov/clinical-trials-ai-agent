#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo 'Please install Python 3.11+ before continuing.' >&2
  exit 1
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo 'Created .env. Add a new, valid OPENAI_API_KEY before using the OpenAI planner.'
fi
python -m pytest -q
