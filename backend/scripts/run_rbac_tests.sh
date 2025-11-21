#!/bin/bash
# RBAC Testing Script
# Runs comprehensive permission tests

set -e  # Exit on error

echo "================================================"
echo "iNSTAiNSTRU RBAC Testing Suite"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Reset test database with fresh data
echo -e "${YELLOW}Step 1: Resetting test database...${NC}"
cd /Users/mehdisaedi/instructly/backend
export USE_TEST_DATABASE=true
python scripts/reset_and_seed_yaml.py

echo ""
echo -e "${GREEN}✓ Database reset complete${NC}"
echo ""

# Step 2: Run the RBAC permission tests
echo -e "${YELLOW}Step 2: Running RBAC permission tests...${NC}"
echo ""

# Make test script executable
chmod +x scripts/test_rbac_permissions.py

# Disable rate limiting for testing
export RATE_LIMIT_ENABLED=false

# Run the tests
python scripts/test_rbac_permissions.py

echo ""
echo -e "${YELLOW}Step 3: Quick smoke tests...${NC}"
echo ""

# Test 1: Student permissions count
echo "Testing student permissions..."
STUDENT_PERMS=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"john.smith@example.com","password":"Test1234"}' \
  | jq '.permissions | length')
echo -e "Student permissions: ${GREEN}$STUDENT_PERMS${NC} (expected: ~10)"

# Test 2: Instructor permissions count
echo "Testing instructor permissions..."
INSTRUCTOR_PERMS=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"sarah.chen@example.com","password":"Test1234"}' \
  | jq '.permissions | length')
echo -e "Instructor permissions: ${GREEN}$INSTRUCTOR_PERMS${NC} (expected: ~13)"

# Test 3: Admin permissions count
echo "Testing admin permissions..."
ADMIN_PERMS=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin@instainstru.com","password":"Test1234"}' \
  | jq '.permissions | length')
echo -e "Admin permissions: ${GREEN}$ADMIN_PERMS${NC} (expected: 30)"

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}RBAC Testing Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Next steps:"
echo "1. Review any failed tests above"
echo "2. Test frontend permission visibility"
echo "3. Create automated test cases for CI/CD"
echo ""
echo "To test frontend permissions, login as:"
echo "- Student: john.smith@example.com"
echo "- Instructor: sarah.chen@example.com"
echo "- Admin: admin@instainstru.com"
echo "Password for all: Test1234"
