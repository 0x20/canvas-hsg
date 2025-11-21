#!/bin/bash

# yt-dlp Update Script for HSG Canvas
# Updates yt-dlp to the latest version and syncs requirements.txt

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Print header
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}  yt-dlp Update Script${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# Check if running from correct directory
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: .venv directory not found${NC}"
    echo "Please run this script from the HSG Canvas project directory"
    exit 1
fi

if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}Error: requirements.txt not found${NC}"
    exit 1
fi

print_header

# Get current version
echo -e "${YELLOW}Checking current yt-dlp version...${NC}"
CURRENT_VERSION=$(.venv/bin/pip show yt-dlp 2>/dev/null | grep "^Version:" | awk '{print $2}')

if [ -z "$CURRENT_VERSION" ]; then
    echo -e "${RED}Error: yt-dlp not found in virtual environment${NC}"
    exit 1
fi

echo -e "Current version: ${GREEN}$CURRENT_VERSION${NC}"
echo ""

# Check if service is running
SERVICE_RUNNING=false
if systemctl is-active --quiet hsg-canvas 2>/dev/null; then
    SERVICE_RUNNING=true
    echo -e "${YELLOW}hsg-canvas service is currently running${NC}"
else
    echo -e "${BLUE}hsg-canvas service is not running${NC}"
fi
echo ""

# Ask about service restart
if [ "$SERVICE_RUNNING" = true ]; then
    echo -e "${YELLOW}Recommendation: Stop service before updating yt-dlp${NC}"
    read -p "Stop hsg-canvas service now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Stopping hsg-canvas service...${NC}"
        sudo systemctl stop hsg-canvas
        echo -e "${GREEN}Service stopped${NC}"
        echo ""
    fi
fi

# Update yt-dlp
echo -e "${BLUE}Updating yt-dlp to latest version...${NC}"
.venv/bin/pip install --upgrade yt-dlp

# Get new version
NEW_VERSION=$(.venv/bin/pip show yt-dlp | grep "^Version:" | awk '{print $2}')

echo ""
echo -e "${GREEN}Update complete!${NC}"
echo -e "Old version: ${YELLOW}$CURRENT_VERSION${NC}"
echo -e "New version: ${GREEN}$NEW_VERSION${NC}"
echo ""

# Check if version changed
if [ "$CURRENT_VERSION" = "$NEW_VERSION" ]; then
    echo -e "${BLUE}Already on latest version, no update needed${NC}"
    echo ""
    echo -e "${BLUE}========================================${NC}\n"
    exit 0
fi

# Update requirements.txt
echo -e "${BLUE}Updating requirements.txt...${NC}"

# Create backup
cp requirements.txt requirements.txt.backup

# Update the yt-dlp version in requirements.txt
sed -i "s/^yt-dlp==.*/yt-dlp==$NEW_VERSION/" requirements.txt

echo -e "${GREEN}requirements.txt updated${NC}"
echo -e "Backup saved as: requirements.txt.backup"
echo ""

# Restart service if it was running
if [ "$SERVICE_RUNNING" = true ]; then
    read -p "Restart hsg-canvas service? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Starting hsg-canvas service...${NC}"
        sudo systemctl start hsg-canvas
        sleep 3
        if systemctl is-active --quiet hsg-canvas; then
            echo -e "${GREEN}Service started successfully${NC}"
        else
            echo -e "${RED}Service failed to start${NC}"
            echo "Check logs with: journalctl -u hsg-canvas -n 50"
        fi
    fi
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}yt-dlp update complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"
