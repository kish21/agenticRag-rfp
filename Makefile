.PHONY: dev test lint seed reset check

dev:
	cp -n .env.example .env 2>/dev/null || true
	docker-compose up -d
	alembic upgrade head
	python scripts/seed_criteria.py
	uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev

test:
	PYTHONPATH=. pytest tests/unit tests/integration -v --tb=short

lint:
	ruff check app/ tests/ tools/ --fix
	cd frontend && npx eslint . 2>/dev/null || true

seed:
	python scripts/seed_criteria.py

reset:
	python scripts/reset_dev_data.py

check:
	python tools/checkpoint_runner.py status
	python tools/drift_detector.py
	PYTHONPATH=. python tools/contract_tests.py
