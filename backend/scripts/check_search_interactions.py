#!/usr/bin/env python
"""Check search events and interactions in the database."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("database_url")

# Create engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Check recent search events and their interactions
print("=== Recent Search Events with Interactions ===")
result = session.execute(
    text(
        """
    SELECT
        se.id as event_id,
        se.search_query,
        se.search_type,
        se.created_at as search_time,
        si.id as interaction_id,
        si.interaction_type,
        si.instructor_id,
        si.result_position,
        si.created_at as interaction_time
    FROM search_events se
    LEFT JOIN search_interactions si ON se.id = si.search_event_id
    ORDER BY se.created_at DESC
    LIMIT 20
"""
    )
)

current_event = None
for row in result:
    if row[0] != current_event:
        current_event = row[0]
        print(f'\nSearch Event #{row[0]}: "{row[1]}" ({row[2]}) at {row[3]}')

    if row[4]:  # If there's an interaction
        print(f"  → Interaction: {row[5]} on instructor {row[6]} at position {row[7]} ({row[8]})")
    else:
        print("  → No interactions yet")

# Summary statistics
print("\n=== Summary ===")
result = session.execute(
    text(
        """
    SELECT
        COUNT(DISTINCT se.id) as total_searches,
        COUNT(DISTINCT si.id) as total_interactions,
        COUNT(DISTINCT CASE WHEN si.id IS NOT NULL THEN se.id END) as searches_with_interactions
    FROM search_events se
    LEFT JOIN search_interactions si ON se.id = si.search_event_id
"""
    )
)
row = result.first()
if row:
    print(f"Total search events: {row[0]}")
    print(f"Total interactions: {row[1]}")
    print(f"Searches with interactions: {row[2]}")
    if row[0] > 0:
        print(f"Interaction rate: {row[2]/row[0]*100:.1f}%")

session.close()
