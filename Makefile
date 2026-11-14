.PHONY: install test run smoke examples check

install:
	python -m pip install -r requirements.txt

run:
	uvicorn app.main:app --reload

test:
	python -m pytest -q

check:
	python -m compileall -q app tests scripts
	python -m pytest -q

smoke:
	bash scripts/smoke.sh

examples:
	python scripts/generate_examples.py
