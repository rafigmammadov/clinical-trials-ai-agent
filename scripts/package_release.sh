#!/usr/bin/env bash
# Build a clean source archive from the repository root.
set -euo pipefail

python -m pytest -q
python -m compileall -q app tests scripts
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git ls-files --error-unmatch .env >/dev/null 2>&1; then
        echo 'ABORT: .env is tracked by Git. Remove it from the index first.' >&2
        exit 1
    fi
fi
if [[ ! -d examples ]] || [[ $(find examples -maxdepth 1 -name '*.json' | wc -l | tr -d ' ') -lt 3 ]]; then
    echo 'ABORT: generate at least 3 actual example JSON files before packaging.' >&2
    echo 'Run: python scripts/generate_examples.py --max-studies 5000' >&2
    exit 1
fi
# When the complete five-example suite is present, validate its real JSON contracts.
if [[ -f examples/time_trend.json && -f examples/phase_distribution.json && \
      -f examples/geography.json && -f examples/network.json && \
      -f examples/comparison.json ]]; then
    python -m scripts.verify_examples
fi

mkdir -p dist
zip -q -r dist/clinical-trials-ai-agent.zip \
  app tests examples scripts docs .github README.md Makefile requirements.txt \
  pytest.ini .env.example .gitignore START_HERE.md \
  -x '*/__pycache__/*' '*.pyc' '*/.DS_Store'
echo 'Created: dist/clinical-trials-ai-agent.zip'
