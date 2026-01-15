#!/bin/bash
#
# DummyProx - One-Click Setup Script for Linux/macOS
#

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}"
echo "  ____                                  ____                  "
echo " |  _ \ _   _ _ __ ___  _ __ ___  _   _|  _ \ _ __ _____  __  "
echo " | | | | | | | '_ \` _ \| '_ \` _ \| | | | |_) | '__/ _ \ \/ /  "
echo " | |_| | |_| | | | | | | | | | | | |_| |  __/| | | (_) >  <   "
echo " |____/ \__,_|_| |_| |_|_| |_| |_|\__, |_|   |_|  \___/_/\_\  "
echo "                                  |___/                       "
echo -e "${NC}"
echo "Nested Proxmox Manager - One-Click Setup"
echo "========================================="
echo ""

# Check for Docker
echo -e "${YELLOW}[1/5]${NC} Checking for Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    echo ""
    echo "Please install Docker first:"
    echo "  - Linux: https://docs.docker.com/engine/install/"
    echo "  - macOS: https://docs.docker.com/desktop/install/mac-install/"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running.${NC}"
    echo "Please start Docker and try again."
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed and running${NC}"

# Check for docker-compose
echo -e "${YELLOW}[2/5]${NC} Checking for Docker Compose..."
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo -e "${YELLOW}Warning: Docker Compose not found, using docker build instead${NC}"
    COMPOSE_CMD=""
fi

if [ -n "$COMPOSE_CMD" ]; then
    echo -e "${GREEN}✓ Docker Compose is available${NC}"
fi

# Clean up old containers and images
echo -e "${YELLOW}[3/5]${NC} Cleaning up old containers and images..."
if [ -n "$COMPOSE_CMD" ]; then
    $COMPOSE_CMD down --rmi all 2>/dev/null || true
else
    docker rm -f dummyprox 2>/dev/null || true
    docker rmi dummyprox 2>/dev/null || true
fi
echo -e "${GREEN}✓ Cleanup complete${NC}"

# Create log directories for volume mount
mkdir -p logs/supervisor logs/nginx

# Build and run
echo -e "${YELLOW}[4/5]${NC} Building and starting DummyProx..."
echo ""

if [ -n "$COMPOSE_CMD" ]; then
    $COMPOSE_CMD build --no-cache
    $COMPOSE_CMD up -d
else
    docker build --no-cache -t dummyprox .
    docker run -d -p 8080:80 --name dummyprox dummyprox
fi

echo ""
echo -e "${GREEN}✓ DummyProx is now running${NC}"

# Open browser
echo -e "${YELLOW}[5/5]${NC} Opening web interface..."
URL="http://localhost:8080"

if command -v xdg-open &> /dev/null; then
    xdg-open "$URL" 2>/dev/null &
elif command -v open &> /dev/null; then
    open "$URL" 2>/dev/null &
elif command -v sensible-browser &> /dev/null; then
    sensible-browser "$URL" 2>/dev/null &
fi

echo ""
echo -e "${GREEN}${BOLD}=========================================${NC}"
echo -e "${GREEN}${BOLD}  DummyProx is ready!${NC}"
echo -e "${GREEN}${BOLD}=========================================${NC}"
echo ""
echo -e "  Web Interface: ${BOLD}http://localhost:8080${NC}"
echo ""
echo "  Commands:"
echo "    Stop:    docker stop dummyprox"
echo "    Start:   docker start dummyprox"
echo "    Logs:    docker logs -f dummyprox"
echo "    Remove:  docker rm -f dummyprox"
echo ""
