"""
Debug cache test to see what's happening with the responses.
"""

import asyncio
from datetime import date, timedelta

import httpx


async def debug_test():
    async with httpx.AsyncClient() as client:
        # Test instructor 1
        instructor_id = 1
        start_date = date.today()
        end_date = start_date + timedelta(days=7)
        url = f"http://localhost:8000/api/public/instructors/{instructor_id}/availability"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        print(f"Testing: {url}")
        print(f"Params: {params}")

        response = await client.get(url, params=params)

        print(f"\nStatus: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")

        if response.status_code != 200:
            print(f"Response body: {response.text}")
        else:
            print("Response: Success")
            print(f"Cache-Control: {response.headers.get('cache-control')}")
            print(f"ETag: {response.headers.get('etag')}")

            # Try with different instructor
            response2 = await client.get("http://localhost:8000/api/public/instructors/2/availability", params=params)
            print(f"\nInstructor 2 status: {response2.status_code}")


if __name__ == "__main__":
    asyncio.run(debug_test())
