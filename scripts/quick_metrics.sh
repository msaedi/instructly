#!/bin/bash

# Quick Codebase Metrics Script
# Provides a fast overview of codebase size

echo "📊 QUICK CODEBASE METRICS"
echo "========================="
echo ""

# Backend Python
echo "🐍 Backend (Python):"
BACKEND_FILES=$(find backend -name "*.py" -not -path "*/venv/*" -not -path "*/__pycache__/*" 2>/dev/null | wc -l | xargs)
BACKEND_LINES=$(find backend -name "*.py" -not -path "*/venv/*" -not -path "*/__pycache__/*" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
echo "  Files: $BACKEND_FILES"
echo "  Lines: $(printf "%'d" $BACKEND_LINES)"
echo ""

# Frontend TypeScript/JavaScript
echo "⚛️  Frontend (TS/JS):"
FRONTEND_FILES=$(find frontend -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) -not -path "*/node_modules/*" -not -path "*/.next/*" 2>/dev/null | wc -l | xargs)
FRONTEND_LINES=$(find frontend -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) -not -path "*/node_modules/*" -not -path "*/.next/*" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
echo "  Files: $FRONTEND_FILES"
echo "  Lines: $(printf "%'d" $FRONTEND_LINES)"
echo ""

# Total
TOTAL_FILES=$((BACKEND_FILES + FRONTEND_FILES))
TOTAL_LINES=$((BACKEND_LINES + FRONTEND_LINES))
echo "📈 Total:"
echo "  Files: $TOTAL_FILES"
echo "  Lines: $(printf "%'d" $TOTAL_LINES)"
echo ""

# Git stats
if [ -d .git ]; then
    COMMITS=$(git rev-list --count HEAD 2>/dev/null || echo "0")
    BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
    echo "📝 Git:"
    echo "  Commits: $COMMITS"
    echo "  Branch: $BRANCH"
    echo ""
fi

# Test counts
echo "🧪 Tests:"
BACKEND_TESTS=$(find backend/tests -name "*.py" 2>/dev/null | wc -l | xargs)
FRONTEND_TESTS=$(find frontend -name "*.test.ts" -o -name "*.test.tsx" -o -name "*.spec.ts" 2>/dev/null | wc -l | xargs)
echo "  Backend test files: $BACKEND_TESTS"
echo "  Frontend test files: $FRONTEND_TESTS"
echo ""

echo "Run 'python scripts/codebase_metrics.py' for detailed analysis"
