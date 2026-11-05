.PHONY: install dataroom ingest test eval eval-onnx demo api mcp web e2e lint typecheck check up

install:
	pip install -e ".[dev]"
	cd web && npm ci

dataroom:          ## regenerate the synthetic data room, gold set and traps
	dealroom generate

ingest:            ## build the index (local OCR, no network)
	dealroom ingest --redact-copies

test:              ## unit and integration tests, coverage >= 90%
	pytest --cov --cov-report=term-missing

eval:              ## regenerate reports/eval.md and reports/results.json (offline)
	dealroom eval

eval-onnx:         ## same with pre-trained ONNX embeddings and cross-encoder (downloads models)
	pip install -e ".[onnx]"
	DEALROOM_RETRIEVAL=onnx dealroom eval

demo:              ## question -> cited answer -> memo -> challenger -> review -> approval
	dealroom demo

api:
	uvicorn dealroom.api.app:app --reload --port 8000

mcp:
	dealroom-mcp

web:
	cd web && npm run dev

e2e:
	cd web && npx playwright test

lint:
	ruff check . && ruff format --check .
	cd web && npm run lint

typecheck:
	python -m mypy
	cd web && npm run typecheck

check: lint typecheck test
	bash scripts/check_hygiene.sh

up:
	docker compose up --build
