import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

database_url = os.getenv("database_url")
print(f"Trying to connect to: {database_url[:50]}...")  # Print first 50 chars

try:
    conn = psycopg2.connect(database_url)
    print("Connection successful!")
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")