# Local quick start

Run these commands from the repository root on macOS or Linux. Use Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` to configure a valid, private `OPENAI_API_KEY`. Keep `PLANNER_MODE=openai` for natural-language interpretation. Never commit credentials. Restart the service after changing configuration.

```bash
python -m pytest -q
python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
curl --fail-with-body http://127.0.0.1:8000/health
bash scripts/smoke.sh
python scripts/generate_examples.py --max-studies 1500
python -m scripts.verify_examples
```

The live smoke test and example generator require connectivity to ClinicalTrials.gov and the configured LLM. The offline tests do not. Inspect `meta.complete`, `meta.visualization_truncated`, `meta.warnings`, and `meta.assumptions` in generated responses.

```bash
python -m compileall -q app tests scripts
bash scripts/package_release.sh
```

For endpoint and schema documentation, see [README.md](README.md). For design tradeoffs, see [docs/DECISIONS.md](docs/DECISIONS.md). For a complete verification checklist, see [docs/QUALITY_GATE.md](docs/QUALITY_GATE.md).
