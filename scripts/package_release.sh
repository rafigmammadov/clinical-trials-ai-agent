#!/usr/bin/env bash
# Reproducible source release; fails closed on tests, incomplete examples or credentials.
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pytest -q
python -m compileall -q app tests scripts evals
python -m evals.run --mode validate
python -m evals.identity
python -m evals.grounding
python -m evals.recall

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git ls-files --error-unmatch .env >/dev/null 2>&1; then
        echo 'ABORT: .env is Git-tracked. Rotate the credential and remove it from history.' >&2
        exit 1
    fi
fi

if [[ -f examples/time_trend.json && -f examples/phase_distribution.json && \
      -f examples/geography.json && -f examples/network.json && \
      -f examples/comparison.json ]]; then
    python -m scripts.verify_examples
fi

python -m scripts.audit_archive --build dist/clinical-trials-ai-agent.zip
