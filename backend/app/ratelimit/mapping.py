# Example route → bucket mapping; extend as needed

ROUTE_BUCKETS: dict[str, str] = {
    "/auth/me": "auth_bootstrap",
    "/api/search/instructors": "read",
    "/instructors": "read",
    "/bookings": "read",
    "/bookings/create": "write",
    "/api/payments/checkout": "financial",
}
