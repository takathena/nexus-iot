#!/bin/bash
# NEXUS IoT - Quick Run Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Cek virtualenv
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Virtualenv tidak ada. Jalankan: make dev${NC}"
    exit 1
fi

# Cek .env
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env tidak ada. Copy dari .env.example${NC}"
    exit 1
fi

# Aktifkan venv
source venv/bin/activate

# Tampilkan info
echo -e "${GREEN}🚀 Starting NEXUS IoT...${NC}"
echo -e "${YELLOW}   Akses: http://localhost:$(grep '^PORT' .env | cut -d= -f2 | tr -d ' ')${NC}"
echo ""

# Run dengan unbuffered output
exec python -u app.py