#!/bin/bash

# HSG Canvas System Monitor
# Monitors all services and processes for the SRS server system

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="http://localhost:80"
SRS_API_URL="http://pixelflut:1985/api/v1"

# Print header
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}  HSG Canvas System Monitor${NC}"
    echo -e "${BLUE}  $(date)${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# Check systemd service status
check_service() {
    local service=$1
    echo -ne "  ${service}: "

    if systemctl is-active --quiet "$service" 2>/dev/null; then
        echo -e "${GREEN}RUNNING${NC}"
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            echo -e "    Enabled: ${GREEN}yes${NC}"
        else
            echo -e "    Enabled: ${YELLOW}no${NC}"
        fi
    else
        echo -e "${RED}STOPPED${NC}"
    fi
}

# Check if process is running
check_process() {
    local name=$1
    local pattern=$2
    echo -ne "  ${name}: "

    if pgrep -f "$pattern" > /dev/null 2>&1; then
        local pid=$(pgrep -f "$pattern" | head -1)
        local cpu=$(ps -p $pid -o %cpu= 2>/dev/null || echo "N/A")
        local mem=$(ps -p $pid -o %mem= 2>/dev/null || echo "N/A")
        echo -e "${GREEN}RUNNING${NC} (PID: $pid, CPU: ${cpu}%, MEM: ${mem}%)"
    else
        echo -e "${RED}NOT RUNNING${NC}"
    fi
}

# Check API endpoint
check_api() {
    echo -ne "  HSG Canvas API: "

    if response=$(curl -s -m 5 "${API_URL}/health" 2>/dev/null); then
        echo -e "${GREEN}RESPONDING${NC}"
        echo "    Response: $response"
    else
        echo -e "${RED}NOT RESPONDING${NC}"
    fi
}

# Get system status from API
get_system_status() {
    if status=$(curl -s -m 5 "${API_URL}/status" 2>/dev/null); then
        echo -e "\n${YELLOW}System Status:${NC}"

        # Parse JSON (requires jq for pretty output, fallback to raw)
        if command -v jq &> /dev/null; then
            echo "$status" | jq '{
                cpu_percent: .cpu_percent,
                memory_percent: .memory_percent,
                temperature_c: .temperature_c,
                disk_usage_percent: .disk_usage_percent,
                active_streams: .active_streams,
                current_playback: .current_playback,
                audio_streaming: .audio_streaming,
                srs_server_connected: .srs_server_connected
            }'
        else
            echo "$status"
        fi
    else
        echo -e "${RED}Could not fetch system status${NC}"
    fi
}

# Check SRS server
check_srs() {
    echo -ne "  SRS Server API: "

    if response=$(curl -s -m 5 "${SRS_API_URL}/streams" 2>/dev/null); then
        echo -e "${GREEN}RESPONDING${NC}"
        if command -v jq &> /dev/null; then
            stream_count=$(echo "$response" | jq '.streams | length' 2>/dev/null || echo "0")
            echo "    Active streams: $stream_count"
        fi
    else
        echo -e "${RED}NOT RESPONDING${NC}"
    fi
}

# Check system resources
check_system_resources() {
    echo -e "\n${YELLOW}System Resources:${NC}"

    # CPU
    if command -v mpstat &> /dev/null; then
        cpu_idle=$(mpstat 1 1 | awk '/Average:/ {print $NF}')
        cpu_usage=$(echo "100 - $cpu_idle" | bc 2>/dev/null || echo "N/A")
        echo "  CPU Usage: ${cpu_usage}%"
    fi

    # Memory
    mem_info=$(free | grep Mem)
    mem_total=$(echo $mem_info | awk '{print $2}')
    mem_used=$(echo $mem_info | awk '{print $3}')
    mem_percent=$(echo "scale=1; $mem_used * 100 / $mem_total" | bc 2>/dev/null || echo "N/A")
    echo "  Memory Usage: ${mem_percent}%"

    # Temperature
    if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
        temp=$(cat /sys/class/thermal/thermal_zone0/temp)
        temp_c=$(echo "scale=1; $temp / 1000" | bc)
        echo "  Temperature: ${temp_c}°C"

        if (( $(echo "$temp_c > 70" | bc -l) )); then
            echo -e "    ${RED}WARNING: High temperature!${NC}"
        fi
    fi

    # Disk usage
    disk_usage=$(df -h / | awk 'NR==2 {print $5}')
    echo "  Disk Usage: $disk_usage"
}

# Main monitoring function
main() {
    print_header

    # Check systemd services
    echo -e "${YELLOW}Systemd Services:${NC}"
    check_service "hsg-canvas"
    check_service "srs-server"
    check_service "raspotify"

    # Check processes
    echo -e "\n${YELLOW}Processes:${NC}"
    check_process "Python App" "python.*main.py"
    check_process "MPV Audio" "mpv.*audio"
    check_process "MPV Video" "mpv.*video"
    check_process "FFmpeg" "ffmpeg.*rtmp"

    # Check APIs
    echo -e "\n${YELLOW}API Health:${NC}"
    check_api
    check_srs

    # Get detailed status from API
    get_system_status

    # Check system resources
    check_system_resources

    echo -e "\n${BLUE}========================================${NC}\n"
}

# Handle arguments
case "${1:-}" in
    -w|--watch)
        # Watch mode - refresh every N seconds
        interval="${2:-5}"
        while true; do
            clear
            main
            sleep "$interval"
        done
        ;;
    -h|--help)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  -w, --watch [INTERVAL]  Watch mode (default: 5 seconds)"
        echo "  -h, --help              Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                      Run once and exit"
        echo "  $0 -w                   Watch mode with 5 second interval"
        echo "  $0 -w 10                Watch mode with 10 second interval"
        ;;
    *)
        main
        ;;
esac
