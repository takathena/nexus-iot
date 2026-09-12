.PHONY: help install dev run test clean docker-build docker-up docker-down backup

PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTEST := $(VENV_BIN)/pytest

help:
	@echo "NEXUS IoT - Available Commands"
	@echo "================================"
	@echo "  make install       - Install dependencies"
	@echo "  make dev           - Setup development environment"
	@echo "  make run           - Run development server"
	@echo "  make run-prod      - Run production server (gunicorn)"
	@echo "  make test          - Run tests"
	@echo "  make clean         - Clean cache & temp files"
	@echo "  make backup        - Backup database"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-up     - Start docker-compose"
	@echo "  make docker-down   - Stop docker-compose"
	@echo "  make docker-logs   - Show docker logs"

# Dependencies
$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	touch $(VENV)/bin/activate

install: $(VENV)/bin/activate
	@echo "✅ Dependencies installed"

# Setup development (hanya jika belum ada)
dev: install
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "📝 Created .env from .env.example"; \
		echo "⚠️  Edit .env dan set SECRET_KEY + IOT_PASSWORD!"; \
		exit 1; \
	fi
	@echo "✅ Development environment ready"

# Run — TIDAK depend on install supaya tidak double-init
run:
	@if [ ! -d $(VENV) ]; then \
		echo "❌ Virtualenv tidak ada. Jalankan: make dev"; \
		exit 1; \
	fi
	@$(VENV_BIN)/python app.py

run-prod:
	@if [ ! -d $(VENV) ]; then \
		echo "❌ Virtualenv tidak ada. Jalankan: make install"; \
		exit 1; \
	fi
	@$(VENV_BIN)/gunicorn -c gunicorn.conf.py wsgi:app

test: install
	@$(PYTEST) tests/ -v

backup:
	@mkdir -p backup
	@$(VENV_BIN)/python -c "import sqlite3; from config import Config; from datetime import datetime; \
	src = sqlite3.connect(Config.DB_PATH); \
	dst = sqlite3.connect(f'backup/iot_{datetime.now().strftime(\"%Y%m%d_%H%M%S\")}.db'); \
	src.backup(dst); dst.close(); src.close(); \
	print('✅ Backup created')"

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build dist *.egg-info 2>/dev/null || true
	@echo "✅ Cleaned"

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-restart:
	docker-compose restart