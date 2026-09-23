# ==========================================
# NEXUS IoT - Makefile
# ==========================================

.PHONY: help dev install run run-prod backup test clean \
        docker-build docker-up docker-down docker-logs docker-restart docker-shell \
        docker-rebuild

GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

VENV        := venv
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
PORT        := $(shell grep '^PORT' .env 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo 5000)
NGINX_PORT  := $(shell grep '^NGINX_PORT' .env 2>/dev/null | cut -d= -f2 | tr -d ' ' || echo 5008)

help:
	@echo "$(GREEN)NEXUS IoT - Available Commands$(NC)"
	@echo ""
	@echo "  $(YELLOW)Development:$(NC)"
	@echo "    make dev            Setup virtualenv & install dependencies"
	@echo "    make install        Install dependencies saja"
	@echo "    make run            Jalankan dev server (python run.py)"
	@echo "    make run-prod       Jalankan production server (Gunicorn)"
	@echo "    make backup         Backup database manual"
	@echo "    make test           Test health endpoint"
	@echo "    make clean          Hapus venv, cache, log, backup lama"
	@echo ""
	@echo "  $(YELLOW)Docker:$(NC)"
	@echo "    make docker-build   Build image"
	@echo "    make docker-up      Start container (background)"
	@echo "    make docker-down    Stop container"
	@echo "    make docker-restart Restart container"
	@echo "    make docker-rebuild Rebuild dari nol + restart"
	@echo "    make docker-logs    Lihat log realtime"
	@echo "    make docker-shell   Masuk ke shell container"
	@echo ""

# ==========================================
# Development
# ==========================================
dev: $(VENV)/bin/activate
	@echo "$(GREEN)Virtualenv ready!$(NC)"
	@echo "$(YELLOW)Jalankan: make run$(NC)"

$(VENV)/bin/activate:
	@echo "$(GREEN)Creating virtualenv...$(NC)"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from .env.example...$(NC)"; \
		cp .env.example .env; \
		echo "$(RED)PENTING: Edit .env, set SECRET_KEY dan IOT_PASSWORD!$(NC)"; \
	fi
	@mkdir -p database logs backup
	@echo "$(GREEN)Setup complete!$(NC)"

install:
	$(PIP) install -r requirements.txt

run:
	@if [ ! -f .env ]; then echo "$(RED).env tidak ada! Jalankan: make dev$(NC)"; exit 1; fi
	@echo "$(GREEN)Starting dev server on port $(PORT)...$(NC)"
	$(PYTHON) run.py

run-prod:
	@if [ ! -f .env ]; then echo "$(RED).env tidak ada!$(NC)"; exit 1; fi
	@echo "$(GREEN)Starting production server (Gunicorn)...$(NC)"
	$(VENV)/bin/gunicorn -w 4 -k gthread --threads 4 -b 0.0.0.0:$(PORT) \
		--access-logfile - --error-logfile - run:app

backup:
	@mkdir -p backup
	$(PYTHON) -c "import sqlite3; from datetime import datetime; \
		src=sqlite3.connect('database/iot.db'); \
		dst=sqlite3.connect(f'backup/manual-{datetime.now():%Y%m%d_%H%M%S}.db'); \
		src.backup(dst); dst.close(); src.close(); \
		print('Backup done')"

test:
	@echo "$(GREEN)Testing health endpoint...$(NC)"
	@curl -s http://localhost:$(PORT)/health | python3 -m json.tool || echo "$(RED)Server tidak jalan$(NC)"

clean:
	@echo "$(YELLOW)Cleaning...$(NC)"
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache
	@echo "$(GREEN)Clean!$(NC)"

# ==========================================
# Docker
# ==========================================
docker-build:
	docker compose build

docker-up:
	@mkdir -p database logs backup
	@chown -R 1000:1000 database logs backup 2>/dev/null || true
	docker compose up -d
	@echo "$(GREEN)Waiting for health check...$(NC)"
	@sleep 15
	@docker compose ps
	@echo ""
	@echo "$(GREEN)Akses: http://localhost:$(NGINX_PORT)$(NC)"

docker-down:
	docker compose down

docker-restart:
	docker compose restart

docker-rebuild:
	docker compose down
	docker compose build --no-cache
	@mkdir -p database logs backup
	@chown -R 1000:1000 database logs backup 2>/dev/null || true
	docker compose up -d
	@echo "$(GREEN)Waiting for health check...$(NC)"
	@sleep 20
	@docker compose ps

docker-logs:
	docker compose logs -f

docker-shell:
	docker compose exec nexus-iot bash