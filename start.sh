#!/bin/bash

export PATH="$HOME/.local/bin:/Users/adam/Library/pnpm:$PATH"

# Grok Voice Agent - Start Script
# Starts both frontend (UI) and backend (agent) concurrently with live logging
# Includes hot reloading for Python backend and checks for existing processes

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Grok Voice Agent...${NC}"

# Create logs directory if it doesn't exist
mkdir -p logs

# Check and kill existing processes
echo -e "${YELLOW}Checking for existing processes...${NC}"

# Kill frontend if running on port 3000
if lsof -i :3000 > /dev/null 2>&1; then
    echo -e "${RED}Killing existing frontend on port 3000...${NC}"
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Kill backend if running on port 7880
if lsof -i :7880 > /dev/null 2>&1; then
    echo -e "${RED}Killing existing backend on port 7880...${NC}"
    lsof -ti:7880 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Start backend (Python agent) with hot reload using watchfiles
echo -e "${YELLOW}Starting backend agent with hot reload...${NC}"
watchfiles 'grok_voice_agent_api.py' -- uv run python grok_voice_agent_api.py dev > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Start frontend (Next.js) in background
echo -e "${YELLOW}Starting frontend UI...${NC}"
cd agent-ui
pnpm dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
echo "Frontend PID: $FRONTEND_PID"

# Wait a moment for processes to start
sleep 3

# Function to cleanup on exit
cleanup() {
    echo -e "\n${RED}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

# Trap SIGINT (Ctrl+C) to cleanup
trap cleanup SIGINT SIGTERM

echo -e "${GREEN}Both services started successfully!${NC}"
echo "Frontend: http://localhost:3000"
echo "Backend logs: logs/backend.log"
echo "Frontend logs: logs/frontend.log"
echo ""
echo -e "${YELLOW}Live logs (press Ctrl+C to stop):${NC}"
echo "=================================================="

# Tail both log files live
tail -f logs/backend.log logs/frontend.log &
TAIL_PID=$!

# Wait for background processes
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true

# Cleanup tail process
kill $TAIL_PID 2>/dev/null || true