# Makefile
.PHONY: help build up down logs shell clean restart db-init status

help:
	@echo "📦 NEXUS IoT - Docker Management"
	@echo ""
	@echo "Available commands:"
	@echo "  make build      - Build Docker image"
	@echo "  make up         - Start containers"
	@echo "  make down       - Stop containers"
	@echo "  make restart    - Restart containers"
	@echo "  make logs       - View all logs"
	@echo "  make status     - Check container status"
	@echo "  make shell      - Open shell in Flask container"
	@echo "  make db-init    - Initialize database"
	@echo ""
	@echo "🌐 Access: http://localhost:5008"

build:
	docker-compose build --no-cache

up:
	mkdir -p database static
	docker-compose up -d
	@echo ""
	@echo "✅ NEXUS IoT is running!"
	@echo "🌐 http://localhost:5008"
	@echo "🔑 Login: admin / admin123 (ubah di .env)"

down:
	docker-compose down

restart: down up

logs:
	docker-compose logs -f

shell:
	docker-compose exec nexus-iot /bin/bash

status:
	docker-compose ps
	@echo ""
	@echo "Health Check:"
	@curl -s http://localhost:5008/health || echo "❌ Not responding"

db-init:
	docker-compose exec nexus-iot python database.py

nginx-reload:
	docker-compose exec nginx nginx -s reload