.PHONY: install test run smoke examples check

install:
	python -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	python -m pytest -q

check:
	python -m compileall -q app tests scripts evals
	python -m pytest -q
	python -m evals.run --mode validate
	python -m evals.identity
	python -m evals.grounding
	python -m evals.recall

smoke:
	bash scripts/smoke.sh

examples:
	python scripts/generate_examples.py
