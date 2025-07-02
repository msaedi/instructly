#!/bin/bash
# Script to find all usage of AvailabilityRepository and its methods

echo "=== Finding files that import AvailabilityRepository ==="
grep -r "from.*availability_repository import\|import.*availability_repository" backend/app/ --include="*.py" | grep -v "__pycache__"

echo -e "\n=== Finding files that use AvailabilityRepository in type hints ==="
grep -r "AvailabilityRepository" backend/app/ --include="*.py" | grep -v "__pycache__" | grep -v "availability_repository.py"

echo -e "\n=== Finding specific method calls ==="
# Key methods we're concerned about
methods=(
    "get_slots_by_availability_id"
    "get_availability_slot_with_details"
    "get_or_create_availability"
    "get_availability_by_date"
    "update_cleared_status"
    "bulk_create_availability"
    "create_availability_with_slots"
    "get_week_availability"
    "slot_exists"
    "find_overlapping_slots"
)

for method in "${methods[@]}"; do
    echo -e "\n--- Usage of $method ---"
    grep -r "\.$method(" backend/app/ --include="*.py" | grep -v "__pycache__" | grep -v "availability_repository.py" | grep -v "test_"
done

echo -e "\n=== Finding repository usage in factories ==="
grep -r "create_availability_repository\|AvailabilityRepository" backend/app/repositories/factory.py

echo -e "\n=== Summary of files to review ==="
echo "Based on imports and usage, you'll need to review these service files:"
grep -r "AvailabilityRepository\|availability_repository" backend/app/services/ --include="*.py" | grep -v "__pycache__" | cut -d: -f1 | sort | uniq
