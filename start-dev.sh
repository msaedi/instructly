#!/bin/bash

# Start Development Environment Script
# This script starts all required services in a tmux session with multiple windows

SESSION_NAME="instructly-dev"

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session with first window (Backend API)
tmux new-session -d -s $SESSION_NAME -n "backend-api" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:backend-api "source venv/bin/activate" C-m
tmux send-keys -t $SESSION_NAME:backend-api "python run_backend.py" C-m

# Window 2: Frontend
tmux new-window -t $SESSION_NAME -n "frontend" -c "$PWD/frontend"
tmux send-keys -t $SESSION_NAME:frontend "npm run dev" C-m

# Window 3: Stripe listener
tmux new-window -t $SESSION_NAME -n "stripe"
tmux send-keys -t $SESSION_NAME:stripe "stripe listen --forward-to localhost:8000/api/payments/webhooks/stripe" C-m

# Window 4: Celery Worker
tmux new-window -t $SESSION_NAME -n "celery-worker" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:celery-worker "source venv/bin/activate" C-m
tmux send-keys -t $SESSION_NAME:celery-worker "python run_celery_worker.py" C-m

# Window 5: Celery Beat
tmux new-window -t $SESSION_NAME -n "celery-beat" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:celery-beat "source venv/bin/activate" C-m
tmux send-keys -t $SESSION_NAME:celery-beat "python run_celery_beat.py" C-m

# Window 6: Celery Flower
tmux new-window -t $SESSION_NAME -n "flower" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:flower "source venv/bin/activate" C-m
tmux send-keys -t $SESSION_NAME:flower "python run_flower.py" C-m

# Window 7: Claude CLI
tmux new-window -t $SESSION_NAME -n "claude"
tmux send-keys -t $SESSION_NAME:claude "source backend/venv/bin/activate" C-m
tmux send-keys -t $SESSION_NAME:claude "claude" C-m

# Window 8: Backend Shell 1
tmux new-window -t $SESSION_NAME -n "backend-shell-1" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:backend-shell-1 "source venv/bin/activate" C-m

# Window 9: Backend Shell 2
tmux new-window -t $SESSION_NAME -n "backend-shell-2" -c "$PWD/backend"
tmux send-keys -t $SESSION_NAME:backend-shell-2 "source venv/bin/activate" C-m

# Start Docker containers (Redis/Dragonfly)
echo "Starting Docker containers..."
cd backend && docker-compose up -d
cd ..

# Attach to the session (starting at window 1)
tmux select-window -t $SESSION_NAME:backend-api
tmux attach-session -t $SESSION_NAME

# Instructions for when tmux exits
echo ""
echo "==============================================="
echo "Tmux session '$SESSION_NAME' has ended."
echo ""
echo "To reattach if still running:"
echo "  tmux attach -t $SESSION_NAME"
echo ""
echo "To see all windows:"
echo "  Ctrl+b w"
echo ""
echo "To switch between windows:"
echo "  Ctrl+b [0-9]  (window number)"
echo "  Ctrl+b n      (next window)"
echo "  Ctrl+b p      (previous window)"
echo ""
echo "To stop all services:"
echo "  ./stop-dev.sh"
echo "==============================================="
