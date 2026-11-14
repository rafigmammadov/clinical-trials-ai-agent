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

# All five real query/JSON pairs are mandatory for this final distribution.
for name in time_trend phase_distribution geography network comparison; do
    if [[ ! -s "examples/${name}.json" ]]; then
        echo "ABORT: missing examples/${name}.json; regenerate the five real registry responses" >&2
        exit 1
    fi
done
python -m scripts.verify_examples

python -m scripts.audit_archive --build dist/clinical-trials-ai-agent.zip
