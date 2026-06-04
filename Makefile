.PHONY: setup backend frontend vision test smoke up down clean

setup: ; ./scripts/setup.sh
backend: ; ./scripts/run-backend.sh
frontend: ; ./scripts/run-frontend.sh
vision: ; ./scripts/run-vision.sh
test: ; cd backend && PYTHONPATH=. ./.venv/bin/python -m pytest tests/ -q
smoke: ; cd backend && PYTHONPATH=. ./.venv/bin/python scripts/smoke.py
up: ; docker compose up --build
down: ; docker compose down
clean: ; rm -rf backend/.cache backend/aifos.db backend/.venv frontend/.next frontend/node_modules vision-ui/node_modules
