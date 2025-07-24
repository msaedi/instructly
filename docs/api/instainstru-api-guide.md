# InstaInstru API Documentation

## Overview

The InstaInstru API provides a RESTful interface for the "Uber of instruction" platform, enabling instant booking of instructors for in-person lessons in NYC.

### Base URLs
- **Production**: `https://instructly.onrender.com`
- **Local Development**: `http://localhost:8000`

### API Version
Current version: `1.0.0`

### General Principles
- All requests and responses use JSON
- Authentication uses JWT Bearer tokens
- Dates are in ISO 8601 format (YYYY-MM-DD)
- Times are in 24-hour format (HH:MM:SS)
- All timestamps are UTC
- Monetary values are in USD
- No trailing slashes on endpoints

## Authentication

### Overview
InstaInstru uses JWT (JSON Web Tokens) for authentication. After successful login, include the token in all authenticated requests.

### Getting Started

#### 1. Register a New User
```bash
curl -X POST https://instructly.onrender.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!",
    "full_name": "John Doe",
    "role": "student"
  }'
```

**Response**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "student",
  "is_active": true
}
```

#### 2. Login
```bash
curl -X POST https://instructly.onrender.com/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=SecurePass123!"
```

**Response**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### 3. Using the Token
Include the token in the Authorization header for all authenticated requests:
```bash
curl -X GET https://instructly.onrender.com/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Token Details
- **Type**: Bearer token
- **Algorithm**: HS256
- **Expiration**: 30 minutes
- **Renewal**: Login again to get a new token

## Rate Limiting

All endpoints are rate limited to prevent abuse and ensure fair usage.

### Rate Limits by Endpoint

| Endpoint | Limit | Window | Key Type |
|----------|-------|--------|----------|
| **General API** | 100 | per minute | IP |
| **POST /auth/login** | 5 | per minute | IP |
| **POST /auth/register** | 10 | per hour | IP |
| **POST /auth/password-reset/request** | 3 | per hour | Email |
| **POST /auth/password-reset/request** | 10 | per hour | IP |
| **POST /bookings** | 20 | per minute | User |
| **POST /bookings/check-availability** | 30 | per minute | User |
| **POST /bookings/send-reminders** | 1 | per hour | IP |

### Rate Limit Headers
All responses include rate limit information:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1625097600
```

### Rate Limit Exceeded Response
```json
{
  "detail": {
    "message": "Rate limit exceeded. Try again in 45 seconds.",
    "code": "RATE_LIMIT_EXCEEDED",
    "retry_after": 45
  }
}
```

## Error Handling

### Standard Error Response Format
```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE",
  "field": "field_name"  // Optional, for validation errors
}
```

### Common HTTP Status Codes
- `200 OK` - Request succeeded
- `201 Created` - Resource created successfully
- `204 No Content` - Request succeeded with no response body
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Authenticated but not authorized
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource conflict (e.g., email already exists)
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

## API Endpoints

### Authentication Endpoints

#### POST /auth/register
Register a new user account.

**Rate Limit**: 10 per hour per IP

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe",
  "role": "student"  // or "instructor"
}
```

**Response (201)**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "student",
  "is_active": true
}
```

**Errors**:
- `400` - Invalid data (weak password, invalid email)
- `409` - Email already registered

---

#### POST /auth/login
Login with email and password.

**Rate Limit**: 5 per minute per IP

**Request Body** (form-urlencoded):
```
username=user@example.com&password=SecurePass123!
```

**Response (200)**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

**Errors**:
- `401` - Invalid credentials

---

#### GET /auth/me
Get current authenticated user information.

**Authentication**: Required

**Response (200)**:
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "student",
  "is_active": true
}
```

### Password Reset Endpoints

#### POST /auth/password-reset/request
Request a password reset email.

**Rate Limit**:
- 3 per hour per email
- 10 per hour per IP

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response (200)** (always returns success to prevent email enumeration):
```json
{
  "message": "If an account exists with this email, you will receive a password reset link shortly."
}
```

---

#### POST /auth/password-reset/confirm
Reset password using token from email.

**Rate Limit**: 10 per minute per IP

**Request Body**:
```json
{
  "token": "reset_token_from_email",
  "new_password": "NewSecurePass123!"
}
```

**Response (200)**:
```json
{
  "message": "Your password has been successfully reset. You can now log in with your new password."
}
```

**Errors**:
- `400` - Invalid, expired, or already used token

---

#### GET /auth/password-reset/verify/{token}
Verify if a reset token is valid.

**Rate Limit**: 20 per minute per IP

**Response (200)**:
```json
{
  "valid": true,
  "email": "u***@example.com"  // Masked for privacy
}
```

### Instructor Endpoints

#### GET /instructors/
Get list of all instructor profiles with optional filtering.

**Authentication**: Not required

**Query Parameters**:
- `skip` (integer, default: 0) - Number of records to skip
- `limit` (integer, default: 100, max: 100) - Number of records to return
- `search` (string, optional) - Text search across instructor name, bio, and skills (case-insensitive)
- `skill` (string, optional) - Filter by specific skill/service (case-insensitive)
- `min_price` (float, optional) - Minimum hourly rate filter (0-1000)
- `max_price` (float, optional) - Maximum hourly rate filter (0-1000)

**Response Format**:
- When no filters are applied: Returns array of instructor profiles (backward compatible)
- When filters are applied: Returns object with instructors array and metadata

**Response (200) - No filters**:
```json
[
  {
    "id": 1,
    "user_id": 123,
    "bio": "Experienced piano teacher...",
    "areas_of_service": ["Manhattan", "Brooklyn"],
    "years_experience": 10,
    "min_advance_booking_hours": 24,
    "buffer_time_minutes": 15,
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z",
    "user": {
      "full_name": "Sarah Chen",
      "email": "sarah.chen@example.com"
    },
    "services": [
      {
        "id": 1,
        "skill": "Piano",
        "hourly_rate": 80.00,
        "description": "Classical and jazz piano lessons",
        "duration_override": null,
        "duration": 60
      }
    ]
  }
]
```

**Response (200) - With filters**:
```json
{
  "instructors": [
    {
      "id": 1,
      "user_id": 123,
      "bio": "Experienced piano teacher with 15 years of teaching experience. Juilliard graduate specializing in classical piano.",
      "areas_of_service": ["Manhattan", "Brooklyn"],
      "years_experience": 15,
      "min_advance_booking_hours": 2,
      "buffer_time_minutes": 0,
      "created_at": "2025-01-15T10:00:00Z",
      "updated_at": "2025-01-15T10:00:00Z",
      "user": {
        "full_name": "Sarah Chen",
        "email": "sarah.chen@example.com"
      },
      "services": [
        {
          "id": 1,
          "skill": "Piano",
          "hourly_rate": 120.00,
          "description": "Classical piano for all levels",
          "duration_override": null,
          "duration": 60,
          "is_active": true
        }
      ]
    }
  ],
  "metadata": {
    "filters_applied": {
      "search": "piano",
      "max_price": 150
    },
    "pagination": {
      "skip": 0,
      "limit": 100,
      "count": 3
    },
    "total_matches": 3,
    "active_instructors": 3
  }
}
```

**Example Requests**:

1. **Search for piano teachers**:
   ```bash
   curl "https://instructly.onrender.com/instructors/?search=piano"
   ```

2. **Find budget-friendly Spanish teachers**:
   ```bash
   curl "https://instructly.onrender.com/instructors/?skill=spanish&max_price=75"
   ```

3. **Search with multiple filters**:
   ```bash
   curl "https://instructly.onrender.com/instructors/?search=music&min_price=50&max_price=150&limit=20"
   ```

4. **Find premium instructors (over $100/hr)**:
   ```bash
   curl "https://instructly.onrender.com/instructors/?min_price=100"
   ```

**Performance Considerations**:
- Text search uses PostgreSQL GIN indexes for fast full-text search
- Skill filtering uses case-insensitive indexes
- Price filtering uses composite indexes on active services
- All filters are applied with AND logic
- Results are deduplicated when joins produce multiple rows
- Only instructors with active services are returned
- Response time typically under 100ms for most queries

**Filter Details**:
- **search**: Searches across instructor name, bio, and all their service skills
- **skill**: Exact skill match (case-insensitive), useful for specific service lookup
- **min_price/max_price**: Filters based on any active service price within range
- All filters can be combined for precise results

---

#### POST /instructors/profile
Create instructor profile (converts user to instructor).

**Authentication**: Required

**Request Body**:
```json
{
  "bio": "Experienced piano teacher with 10 years of teaching experience",
  "areas_of_service": ["Manhattan", "Brooklyn"],
  "years_experience": 10,
  "min_advance_booking_hours": 24,
  "buffer_time_minutes": 15,
  "services": [
    {
      "skill": "Piano",
      "hourly_rate": 80.00,
      "description": "Classical and jazz piano lessons",
      "duration_override": 60
    }
  ]
}
```

**Response (201)**: Same as GET /instructors/ single profile

**Errors**:
- `400` - Profile already exists
- `403` - Not authenticated

---

#### GET /instructors/profile
Get current instructor's profile.

**Authentication**: Required (instructor only)

**Response (200)**: Same as single instructor profile

**Errors**:
- `403` - Not an instructor
- `404` - Profile not found

---

#### PUT /instructors/profile
Update instructor profile.

**Authentication**: Required (instructor only)

**Request Body** (all fields optional):
```json
{
  "bio": "Updated bio",
  "areas_of_service": ["Manhattan", "Brooklyn", "Queens"],
  "years_experience": 11,
  "services": [
    {
      "skill": "Piano",
      "hourly_rate": 90.00,
      "description": "Updated description"
    }
  ]
}
```

**Response (200)**: Updated profile

**Note**: Services with existing bookings will be soft-deleted (marked inactive) rather than removed.

---

#### DELETE /instructors/profile
Delete instructor profile and revert to student role.

**Authentication**: Required (instructor only)

**Response (204)**: No content

**Note**: This will soft-delete all services to preserve booking history.

---

#### GET /instructors/{instructor_id}
Get specific instructor's profile by user ID.

**Authentication**: Not required

**Response (200)**: Single instructor profile

**Errors**:
- `404` - Instructor not found

### Availability Management Endpoints

#### GET /instructors/availability-windows/week
Get availability for a specific week.

**Authentication**: Required (instructor only)

**Query Parameters**:
- `start_date` (date, required) - Monday of the week

**Response (200)**:
```json
{
  "2025-01-20": [
    {
      "instructor_id": 123,
      "specific_date": "2025-01-20",
      "start_time": "09:00:00",
      "end_time": "10:00:00"
    },
    {
      "instructor_id": 123,
      "specific_date": "2025-01-20",
      "start_time": "14:00:00",
      "end_time": "16:00:00"
    }
  ],
  "2025-01-21": []
  // ... other days of the week
}
```

---

#### POST /instructors/availability-windows/week
Save availability for specific dates in a week.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "schedule": [
    {
      "date": "2025-01-20",
      "start_time": "09:00",
      "end_time": "10:00"
    },
    {
      "date": "2025-01-20",
      "start_time": "14:00",
      "end_time": "16:00"
    }
  ],
  "clear_existing": true,
  "week_start": "2025-01-20"  // Optional Monday date
}
```

**Response (200)**: Success confirmation with updated availability

---

#### POST /instructors/availability-windows/copy-week
Copy availability from one week to another.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "from_week_start": "2025-01-20",
  "to_week_start": "2025-01-27"
}
```

**Response (200)**: Confirmation with copied slots count

---

#### POST /instructors/availability-windows/apply-to-date-range
Apply a week's pattern to a date range.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "from_week_start": "2025-01-20",
  "start_date": "2025-02-01",
  "end_date": "2025-02-28"
}
```

**Response (200)**: Confirmation with applied slots count

---

#### POST /instructors/availability-windows/specific-date
Add availability for a single date.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "specific_date": "2025-01-25",
  "start_time": "10:00",
  "end_time": "12:00"
}
```

**Response (200)**:
```json
{
  "id": 456,
  "instructor_id": 123,
  "specific_date": "2025-01-25",
  "start_time": "10:00:00",
  "end_time": "12:00:00"
}
```

---

#### GET /instructors/availability-windows/
Get all availability with optional date filtering.

**Authentication**: Required (instructor only)

**Query Parameters**:
- `start_date` (date, optional) - Filter from this date
- `end_date` (date, optional) - Filter to this date

**Response (200)**: Array of availability slots

---

#### PATCH /instructors/availability-windows/{window_id}
Update a specific time slot.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "start_time": "09:30",
  "end_time": "10:30"
}
```

**Response (200)**: Updated slot

---

#### DELETE /instructors/availability-windows/{window_id}
Delete a specific time slot.

**Authentication**: Required (instructor only)

**Response (200)**:
```json
{
  "message": "Availability time slot deleted"
}
```

---

#### GET /instructors/availability-windows/blackout-dates
Get instructor's blackout (vacation) dates.

**Authentication**: Required (instructor only)

**Response (200)**:
```json
[
  {
    "id": 1,
    "instructor_id": 123,
    "date": "2025-02-14",
    "reason": "Valentine's Day",
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

---

#### POST /instructors/availability-windows/blackout-dates
Add a blackout date.

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "date": "2025-02-14",
  "reason": "Valentine's Day"  // Optional
}
```

**Response (200)**: Created blackout date

---

#### DELETE /instructors/availability-windows/blackout-dates/{id}
Remove a blackout date.

**Authentication**: Required (instructor only)

**Response (200)**:
```json
{
  "message": "Blackout date deleted"
}
```

### Booking Endpoints

#### POST /bookings/
Create a new booking (instant confirmation).

**Authentication**: Required
**Rate Limit**: 20 per minute per user

**Request Body**:
```json
{
  "instructor_id": 123,
  "service_id": 456,
  "booking_date": "2025-01-25",
  "start_time": "14:00",
  "end_time": "15:00",
  "student_note": "First time learning piano",
  "meeting_location": "123 Main St, Apt 4B",
  "location_type": "student_home"  // or "instructor_location", "neutral"
}
```

**Response (201)**:
```json
{
  "id": 789,
  "student_id": 111,
  "instructor_id": 123,
  "service_id": 456,
  "booking_date": "2025-01-25",
  "start_time": "14:00:00",
  "end_time": "15:00:00",
  "service_name": "Piano",
  "hourly_rate": 80.00,
  "total_price": 80.00,
  "duration_minutes": 60,
  "status": "CONFIRMED",
  "location_type": "student_home",
  "meeting_location": "123 Main St, Apt 4B",
  "service_area": "Manhattan",
  "student_note": "First time learning piano",
  "instructor_note": null,
  "created_at": "2025-01-20T10:00:00Z",
  "confirmed_at": "2025-01-20T10:00:00Z",
  "student": {
    "id": 111,
    "full_name": "John Doe",
    "email": "john.doe@example.com"
  },
  "instructor": {
    "id": 123,
    "full_name": "Sarah Chen",
    "email": "sarah.chen@example.com"
  },
  "service": {
    "id": 456,
    "skill": "Piano",
    "description": "Classical and jazz piano lessons"
  }
}
```

**Errors**:
- `400` - Invalid booking data
- `409` - Time slot not available

---

#### GET /bookings/
Get user's bookings with pagination.

**Authentication**: Required

**Query Parameters**:
- `status` (string, optional) - Filter by status: CONFIRMED, COMPLETED, CANCELLED
- `upcoming_only` (boolean, default: false) - Only show future bookings
- `page` (integer, default: 1) - Page number
- `per_page` (integer, default: 20, max: 100) - Items per page

**Response (200)**:
```json
{
  "bookings": [
    // Array of booking objects
  ],
  "total": 45,
  "page": 1,
  "per_page": 20
}
```

---

#### GET /bookings/upcoming
Get upcoming bookings for dashboard widget.

**Authentication**: Required

**Query Parameters**:
- `limit` (integer, default: 5, max: 20) - Number of bookings to return

**Response (200)**: Array of simplified booking objects

---

#### GET /bookings/stats
Get booking statistics (instructors only).

**Authentication**: Required (instructor only)

**Response (200)**:
```json
{
  "total_bookings": 150,
  "upcoming_bookings": 12,
  "completed_bookings": 135,
  "cancelled_bookings": 3,
  "total_earnings": 12000.00,
  "this_month_earnings": 2400.00,
  "average_rating": null  // Future feature
}
```

---

#### GET /bookings/{booking_id}
Get full booking details.

**Authentication**: Required (participant only)

**Response (200)**: Full booking object

---

#### GET /bookings/{booking_id}/preview
Get booking preview (lightweight version).

**Authentication**: Required (participant only)

**Response (200)**:
```json
{
  "booking_id": 789,
  "student_name": "John Doe",
  "instructor_name": "Sarah Chen",
  "service_name": "Piano",
  "booking_date": "2025-01-25",
  "start_time": "14:00:00",
  "end_time": "15:00:00",
  "duration_minutes": 60,
  "location_type": "student_home",
  "location_type_display": "Student's Home",
  "meeting_location": "123 Main St, Apt 4B",
  "service_area": "Manhattan",
  "status": "CONFIRMED",
  "student_note": "First time learning piano",
  "total_price": 80.00
}
```

---

#### PATCH /bookings/{booking_id}
Update booking details (instructor only).

**Authentication**: Required (instructor only)

**Request Body**:
```json
{
  "instructor_note": "Bring beginner sheet music",
  "meeting_location": "Updated location"
}
```

**Response (200)**: Updated booking

---

#### POST /bookings/{booking_id}/cancel
Cancel a booking.

**Authentication**: Required (participant only)

**Request Body**:
```json
{
  "reason": "Schedule conflict"
}
```

**Response (200)**: Updated booking with CANCELLED status

---

#### POST /bookings/{booking_id}/complete
Mark booking as completed (instructor only).

**Authentication**: Required (instructor only)

**Response (200)**: Updated booking with COMPLETED status

---

#### POST /bookings/check-availability
Check if a time slot is available for booking.

**Authentication**: Required
**Rate Limit**: 30 per minute per user

**Request Body**:
```json
{
  "instructor_id": 123,
  "service_id": 456,
  "booking_date": "2025-01-25",
  "start_time": "14:00",
  "end_time": "15:00"
}
```

**Response (200)**:
```json
{
  "available": true,
  "reason": null,
  "min_advance_hours": 24,
  "conflicts_with": []
}
```

### Public Endpoints (No Authentication Required)

#### GET /api/public/instructors/{instructor_id}/availability
Get instructor's available time slots for booking.

**Query Parameters**:
- `start_date` (date, required) - Start of date range
- `end_date` (date, optional) - End of date range (max 30-90 days based on config)

**Response (200)** (Full detail level):
```json
{
  "instructor_id": 123,
  "instructor_name": "Sarah Chen",
  "availability_by_date": {
    "2025-01-25": {
      "date": "2025-01-25",
      "available_slots": [
        {
          "start_time": "09:00",
          "end_time": "10:00"
        },
        {
          "start_time": "14:00",
          "end_time": "16:00"
        }
      ],
      "is_blackout": false
    }
  },
  "timezone": "America/New_York",
  "total_available_slots": 2,
  "earliest_available_date": "2025-01-25"
}
```

**Response (200)** (Summary detail level):
```json
{
  "instructor_id": 123,
  "instructor_name": "Sarah Chen",
  "availability_summary": {
    "2025-01-25": {
      "date": "2025-01-25",
      "morning_available": true,
      "afternoon_available": true,
      "evening_available": false,
      "total_hours": 3.0
    }
  },
  "timezone": "America/New_York",
  "total_available_days": 5,
  "detail_level": "summary"
}
```

**Response (200)** (Minimal detail level):
```json
{
  "instructor_id": 123,
  "instructor_name": "Sarah Chen",
  "has_availability": true,
  "earliest_available_date": "2025-01-25",
  "timezone": "America/New_York"
}
```

**Errors**:
- `404` - Instructor not found
- `400` - Invalid date range

---

#### GET /api/public/instructors/{instructor_id}/next-available
Find the next available booking slot.

**Query Parameters**:
- `duration_minutes` (integer, default: 60) - Required duration

**Response (200)**:
```json
{
  "found": true,
  "date": "2025-01-25",
  "start_time": "14:00:00",
  "end_time": "15:00:00",
  "duration_minutes": 60
}
```

**Response (200)** (Not found):
```json
{
  "found": false,
  "message": "No available slots found in the next 30 days"
}
```

### Metrics Endpoints (Limited Access)

#### GET /metrics/health
Basic health check endpoint.

**Response (200)**:
```json
{
  "status": "healthy",
  "service": "InstaInstru API"
}
```

---

#### GET /metrics/performance
Get performance metrics (admin only).

**Authentication**: Required (admin users only)

**Response (200)**: Detailed performance metrics

---

#### GET /metrics/rate-limits
Get rate limit statistics.

**Authentication**: Required

**Response (200)**:
```json
{
  "total_keys": 42,
  "by_type": {
    "general": 35,
    "auth": 7
  },
  "top_limited": [
    {
      "key": "rate_limit:general:192.168.1.1",
      "requests": 95,
      "ttl_seconds": 45
    }
  ]
}
```

### Production Monitoring Endpoints (API Key Required)

#### GET /api/monitoring/dashboard
Comprehensive monitoring dashboard data.

**Authentication**: X-Monitoring-API-Key header required in production

**Response (200)**:
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "request_count": 1500,
  "avg_response_time_ms": 85.3,
  "error_rate_percent": 0.5,
  "database_pool": {
    "size": 5,
    "checked_out": 2,
    "overflow": 0,
    "total": 5
  },
  "cache": {
    "status": "connected",
    "hit_rate_percent": 92.5,
    "keys_count": 150
  },
  "memory": {
    "used_mb": 312,
    "available_mb": 712,
    "percent": 43.8
  }
}
```

---

#### GET /api/monitoring/slow-queries
Get recent slow database queries.

**Authentication**: X-Monitoring-API-Key header required in production

**Response (200)**:
```json
{
  "slow_queries": [
    {
      "timestamp": "2025-07-24T18:30:45.123Z",
      "duration_ms": 156.7,
      "query": "SELECT * FROM bookings WHERE...",
      "caller": "BookingService.get_instructor_bookings"
    }
  ],
  "threshold_ms": 100,
  "count": 3
}
```

---

#### GET /api/monitoring/slow-requests
Get recent slow HTTP requests.

**Authentication**: X-Monitoring-API-Key header required in production

**Response (200)**:
```json
{
  "slow_requests": [
    {
      "timestamp": "2025-07-24T18:35:12.456Z",
      "method": "GET",
      "path": "/api/availability/week/123/2025-07-24",
      "duration_ms": 245.8,
      "status_code": 200
    }
  ],
  "threshold_ms": 200,
  "count": 5
}
```

---

#### GET /api/monitoring/cache/extended-stats
Get detailed cache statistics including Upstash metrics.

**Authentication**: X-Monitoring-API-Key header required in production

**Response (200)**:
```json
{
  "basic_stats": {
    "hit_rate_percent": 92.5,
    "total_requests": 10000,
    "hits": 9250,
    "misses": 750
  },
  "upstash_stats": {
    "commands_processed": 8500,
    "bandwidth_used_mb": 125.5,
    "daily_limit_percent": 42.3,
    "pipeline_efficiency": 0.78
  }
}
```

## TypeScript Types

```typescript
// User Types
export interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'student' | 'instructor';
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
}

// Instructor Types
export interface Service {
  id: number;
  skill: string;
  hourly_rate: number;
  description?: string;
  duration_override?: number;
  duration: number;
  is_active?: boolean;  // Included when filtering is applied
}

export interface InstructorProfile {
  id: number;
  user_id: number;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours: number;
  buffer_time_minutes: number;
  created_at: string;
  updated_at?: string;
  user: {
    full_name: string;
    email: string;
  };
  services: Service[];
}

// Instructor Filtering Types
export interface InstructorFilterParams {
  search?: string;
  skill?: string;
  min_price?: number;
  max_price?: number;
  skip?: number;
  limit?: number;
}

export interface InstructorFilterResponse {
  instructors: InstructorProfile[];
  metadata: {
    filters_applied: Record<string, any>;
    pagination: {
      skip: number;
      limit: number;
      count: number;
    };
    total_matches: number;
    active_instructors: number;
  };
}

// Availability Types
export interface TimeSlot {
  start_time: string;
  end_time: string;
}

export interface AvailabilitySlot {
  id: number;
  instructor_id: number;
  specific_date: string;
  start_time: string;
  end_time: string;
}

export interface BlackoutDate {
  id: number;
  instructor_id: number;
  date: string;
  reason?: string;
  created_at: string;
}

// Booking Types
export interface Booking {
  id: number;
  student_id: number;
  instructor_id: number;
  service_id: number;
  booking_date: string;
  start_time: string;
  end_time: string;
  service_name: string;
  hourly_rate: number;
  total_price: number;
  duration_minutes: number;
  status: 'PENDING' | 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
  location_type?: 'student_home' | 'instructor_location' | 'neutral';
  meeting_location?: string;
  service_area?: string;
  student_note?: string;
  instructor_note?: string;
  created_at: string;
  confirmed_at?: string;
  completed_at?: string;
  cancelled_at?: string;
  student: {
    id: number;
    full_name: string;
    email: string;
  };
  instructor: {
    id: number;
    full_name: string;
    email: string;
  };
  service: {
    id: number;
    skill: string;
    description?: string;
  };
}

export interface BookingCreateRequest {
  instructor_id: number;
  service_id: number;
  booking_date: string;
  start_time: string;
  end_time: string;
  student_note?: string;
  meeting_location?: string;
  location_type?: 'student_home' | 'instructor_location' | 'neutral';
}

// Public API Types
export interface PublicTimeSlot {
  start_time: string;
  end_time: string;
}

export interface PublicDayAvailability {
  date: string;
  available_slots: PublicTimeSlot[];
  is_blackout: boolean;
}

export interface PublicInstructorAvailability {
  instructor_id: number;
  instructor_name: string;
  availability_by_date: Record<string, PublicDayAvailability>;
  timezone: string;
  total_available_slots: number;
  earliest_available_date?: string;
}

// Error Response
export interface ErrorResponse {
  detail: string;
  code?: string;
  field?: string;
}

export interface RateLimitError {
  detail: {
    message: string;
    code: 'RATE_LIMIT_EXCEEDED';
    retry_after: number;
  };
}
```

## Examples

### Complete Booking Flow
```typescript
// 1. Search for instructors with filtering
// Example: Find piano teachers under $100/hr
const response = await fetch('https://instructly.onrender.com/instructors/?skill=piano&max_price=100');
const result = await response.json();

// Check if response includes metadata (filters were applied)
const instructors = result.instructors || result;

// 2. Check instructor availability (public endpoint)
const availabilityResponse = await fetch(
  'https://instructly.onrender.com/api/public/instructors/123/availability?start_date=2025-01-20&end_date=2025-01-26'
);
const availability = await availabilityResponse.json();

// 3. Register/Login as student
const loginResponse = await fetch('https://instructly.onrender.com/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'username=student@example.com&password=SecurePass123!'
});
const { access_token } = await loginResponse.json();

// 4. Create booking
const bookingResponse = await fetch('https://instructly.onrender.com/bookings/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    instructor_id: 123,
    service_id: 456,
    booking_date: '2025-01-25',
    start_time: '14:00',
    end_time: '15:00',
    student_note: 'Looking forward to my first lesson!',
    location_type: 'neutral'
  })
});
const booking = await bookingResponse.json();
```

### Instructor Search and Filtering
```typescript
// 1. Simple text search
const searchResponse = await fetch('https://instructly.onrender.com/instructors/?search=music');
const searchResult = await searchResponse.json();
console.log(`Found ${searchResult.metadata.active_instructors} music instructors`);

// 2. Filter by specific skill
const skillResponse = await fetch('https://instructly.onrender.com/instructors/?skill=yoga');
const skillResult = await skillResponse.json();
const yogaInstructors = skillResult.instructors;

// 3. Price range filtering
const budgetResponse = await fetch('https://instructly.onrender.com/instructors/?min_price=20&max_price=50');
const budgetResult = await budgetResponse.json();
console.log(`Found ${budgetResult.metadata.total_matches} budget-friendly options`);

// 4. Combined filters for precise results
const params = new URLSearchParams({
  search: 'piano',
  max_price: '100',
  skip: '0',
  limit: '10'
});
const comboResponse = await fetch(`https://instructly.onrender.com/instructors/?${params}`);
const comboResult = await comboResponse.json();

// 5. Handle backward-compatible responses
async function getInstructors(filters?: InstructorFilterParams) {
  const url = new URL('https://instructly.onrender.com/instructors/');
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined) url.searchParams.append(key, String(value));
    });
  }

  const response = await fetch(url);
  const data = await response.json();

  // Check if filtering was applied (response has metadata)
  if (data.metadata) {
    return {
      instructors: data.instructors,
      totalFound: data.metadata.total_matches,
      filtersUsed: data.metadata.filters_applied
    };
  }

  // No filters - simple array response
  return {
    instructors: data,
    totalFound: data.length,
    filtersUsed: {}
  };
}
```

### Instructor Availability Management
```typescript
// 1. Login as instructor
const token = 'your_instructor_token';

// 2. Get current week availability
const weekResponse = await fetch(
  'https://instructly.onrender.com/instructors/availability-windows/week?start_date=2025-01-20',
  {
    headers: { 'Authorization': `Bearer ${token}` }
  }
);
const weekAvailability = await weekResponse.json();

// 3. Update availability for the week
const updateResponse = await fetch(
  'https://instructly.onrender.com/instructors/availability-windows/week',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      schedule: [
        { date: '2025-01-20', start_time: '09:00', end_time: '12:00' },
        { date: '2025-01-20', start_time: '14:00', end_time: '17:00' },
        { date: '2025-01-22', start_time: '10:00', end_time: '15:00' }
      ],
      clear_existing: true,
      week_start: '2025-01-20'
    })
  }
);

// 4. Copy this week's schedule to next week
const copyResponse = await fetch(
  'https://instructly.onrender.com/instructors/availability-windows/copy-week',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      from_week_start: '2025-01-20',
      to_week_start: '2025-01-27'
    })
  }
);
```

## Best Practices

### 1. Authentication
- Store tokens securely (HttpOnly cookies or secure storage)
- Refresh tokens before expiration
- Never expose tokens in URLs or logs

### 2. Error Handling
- Always check response status codes
- Implement exponential backoff for rate limits
- Log errors for debugging
- Show user-friendly error messages

### 3. Rate Limiting
- Implement client-side rate limiting
- Cache responses when appropriate
- Use the Retry-After header
- Monitor X-RateLimit headers

### 4. Date/Time Handling
- Always use ISO 8601 format for dates
- Use 24-hour format for times
- Consider timezone differences
- Validate date ranges client-side

### 5. Performance
- Use pagination for list endpoints
- Implement proper caching strategies
- Minimize API calls
- Use batch operations where available

## Webhook Events (Future Feature)
Currently, InstaInstru does not support webhooks. This may be added in future versions for real-time updates.

## API Versioning
The API currently uses URL-based versioning. Future versions may introduce:
- Header-based versioning
- Breaking change notifications
- Deprecation timelines

## Support
For API support, contact: support@instainstru.com

## Changelog
- **v1.1.0** (2025-01-13): Instructor search and filtering
  - Added filtering to GET /instructors/ endpoint
  - Text search across name, bio, and skills
  - Skill-specific filtering
  - Price range filtering (min/max)
  - Backward-compatible response format
  - Performance optimizations with PostgreSQL indexes

- **v1.0.0** (2025-01-15): Initial API release
  - Authentication endpoints
  - Instructor management
  - Availability management
  - Booking system
  - Public availability endpoints
