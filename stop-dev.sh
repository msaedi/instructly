#!/bin/bash

# Stop Development Environment Script
# This script stops all services and cleans up

SESSION_NAME="instructly-dev"

echo "Stopping iNSTAiNSTRU development environment..."

# Kill tmux session
echo "Stopping tmux session..."
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Stop Docker containers
echo "Stopping Docker containers..."
cd backend && docker-compose down
cd ..

echo "All services stopped."
