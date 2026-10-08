.PHONY: init up down logs health test

init:
	cp -n .env.example .env || true
	python scripts/bootstrap_env.py

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

health:
	python scripts/healthcheck.py

test:
	python -m pytest tests -q
