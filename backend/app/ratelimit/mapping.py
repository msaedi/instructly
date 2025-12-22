# Example route → bucket mapping; extend as needed

ROUTE_BUCKETS: dict[str, str] = {
    "/auth/me": "auth_bootstrap",
    "/api/v1/search/instructors": "read",
    "/api/v1/instructors": "read",
    "/api/v1/bookings": "read",
    "/api/v1/bookings/create": "write",
    "/api/v1/payments/checkout": "financial",
}
