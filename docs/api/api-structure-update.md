# API Structure Update Documentation

## Date: 2024-08-22
## Version: 2.0.0

## Overview
This document outlines the updated API endpoint structure for InstaInstru, focusing on consistency, clarity, and proper separation of concerns.

## Key Changes

### 1. Instructor Endpoints Consolidation
All instructor-related endpoints are now under `/instructors/*` (plural, consistent)

### 2. Availability Endpoints Simplification
- **OLD**: `/instructors/availability-windows/*`
- **NEW**: `/instructors/availability/*`

### 3. Account Management Separation
Account lifecycle management moved from instructor routes to dedicated account routes:
- **OLD**: `/instructors/{id}/suspend`, `/instructors/{id}/deactivate`
- **NEW**: `/api/account/suspend`, `/api/account/deactivate`

## Complete API Structure

### Authentication & Account Management

#### Authentication (`/api/auth/*`)
```
POST   /api/auth/register               - Register new user
POST   /api/auth/login                  - Login (returns JWT)
GET    /api/auth/me                     - Get current user
POST   /api/auth/logout                 - Logout

# 2FA
POST   /api/auth/2fa/setup/initiate     - Start 2FA setup
POST   /api/auth/2fa/setup/verify       - Verify TOTP code
POST   /api/auth/2fa/verify-login       - Verify 2FA on login
POST   /api/auth/2fa/disable            - Disable 2FA
POST   /api/auth/2fa/regenerate-backup-codes - Get new backup codes
GET    /api/auth/2fa/status             - Check 2FA status

# Password Reset
POST   /api/auth/password-reset/request - Request reset
POST   /api/auth/password-reset/confirm - Confirm with token
GET    /api/auth/password-reset/verify/{token} - Verify token
```

#### Account Management (`/api/account/*`)
```
POST   /api/account/suspend             - Suspend account
POST   /api/account/deactivate          - Deactivate account
POST   /api/account/reactivate          - Reactivate account
GET    /api/account/status              - Check account status
```

### Instructor Management

#### Public Instructor Endpoints (`/instructors/*`)
```
GET    /instructors/                    - List all instructors (paginated)
GET    /instructors/{id}                - Get specific instructor profile
GET    /instructors/{id}/coverage       - Get instructor's service areas
```

#### Instructor Profile Management (`/instructors/me`)
```
POST   /instructors/me                  - Create instructor profile
GET    /instructors/me                  - Get own instructor profile
PUT    /instructors/me                  - Update instructor profile
DELETE /instructors/me                  - Delete instructor profile
```

#### Instructor Availability (`/instructors/availability/*`)
```
# Weekly Availability
GET    /instructors/availability/week   - Get week's availability
POST   /instructors/availability/week   - Set week's availability
POST   /instructors/availability/copy-week - Copy week to another

# Specific Dates
POST   /instructors/availability/specific-date - Add specific date availability
GET    /instructors/availability/       - List all availability
PATCH  /instructors/availability/{window_id} - Update window
DELETE /instructors/availability/{window_id} - Delete window

# Bulk Operations
PATCH  /instructors/availability/bulk-update - Update multiple windows
POST   /instructors/availability/apply-to-date-range - Apply pattern to range
POST   /instructors/availability/week/validate-changes - Validate before save

# Blackout Dates
GET    /instructors/availability/blackout-dates - List blackouts
POST   /instructors/availability/blackout-dates - Add blackout
DELETE /instructors/availability/blackout-dates/{id} - Remove blackout

# Booked Slots View
GET    /instructors/availability/week/booked-slots - View booked times
```

#### Instructor Bookings Management (`/instructors/bookings/*`)
```
GET    /instructors/bookings/pending-completion - Get pending lessons
GET    /instructors/bookings/completed  - Get completed lessons
POST   /instructors/bookings/{id}/complete - Mark lesson complete
POST   /instructors/bookings/{id}/dispute - Dispute completion
```

### Student Bookings

#### Booking Operations (`/bookings/*`)
```
# CRUD Operations
GET    /bookings/                       - List user's bookings
POST   /bookings/                       - Create new booking
GET    /bookings/{id}                   - Get booking details
PATCH  /bookings/{id}                   - Update booking
GET    /bookings/{id}/preview           - Preview booking changes

# Booking Actions
POST   /bookings/{id}/cancel            - Cancel booking
POST   /bookings/{id}/complete          - Complete booking
POST   /bookings/{id}/confirm-payment   - Confirm payment method

# Utilities
POST   /bookings/check-availability     - Check time availability
GET    /bookings/upcoming               - Get upcoming bookings
GET    /bookings/stats                  - Get booking statistics
POST   /bookings/send-reminders         - Trigger reminder emails
```

### Search & Discovery

#### Search (`/api/search/*`)
```
GET    /api/search/instructors          - Search instructors
GET    /api/search/services             - Search services
GET    /api/search/suggestions          - Get search suggestions
```

#### Public Data (`/api/public/*`)
```
GET    /api/public/instructors/{id}/availability - Public availability view
GET    /api/public/instructors/{id}/next-available - Next available slot
GET    /api/public/categories           - List service categories
GET    /api/public/services             - List all services
```

### User Features

#### Favorites (`/api/favorites/*`)
```
GET    /api/favorites/                  - List favorited instructors
POST   /api/favorites/{instructor_id}   - Add favorite
DELETE /api/favorites/{instructor_id}   - Remove favorite
GET    /api/favorites/check/{instructor_id} - Check if favorited
```

#### User Addresses (`/api/addresses/*`)
```
GET    /api/addresses/me                - Get user's addresses
POST   /api/addresses/me                - Add new address
PATCH  /api/addresses/me/{id}           - Update address
DELETE /api/addresses/me/{id}           - Delete address

# Google Places Integration
GET    /api/addresses/places/autocomplete - Autocomplete addresses
GET    /api/addresses/places/details    - Get place details

# Service Areas
GET    /api/addresses/service-areas/me  - Get instructor's areas
PUT    /api/addresses/service-areas/me  - Update service areas
GET    /api/addresses/regions/neighborhoods - List neighborhoods
```

#### Messages (`/api/messages/*`)
```
GET    /api/messages/conversations      - List conversations
GET    /api/messages/conversation/{id}  - Get conversation
POST   /api/messages/send               - Send message
PATCH  /api/messages/{id}/read          - Mark as read
GET    /api/messages/unread-count       - Get unread count
```

### Payments (`/api/payments/*`)
```
# Payment Methods
GET    /api/payments/methods            - List payment methods
POST   /api/payments/methods            - Add payment method
DELETE /api/payments/methods/{id}       - Remove method
POST   /api/payments/methods/{id}/default - Set as default

# Transactions
GET    /api/payments/transactions       - Transaction history
GET    /api/payments/transactions/{id}  - Transaction details

# Platform Credits
GET    /api/payments/credits            - Available credits
POST   /api/payments/credits/apply      - Apply credit to booking

# Stripe Connect (Instructors)
POST   /api/payments/connect/onboard    - Start Stripe onboarding
GET    /api/payments/connect/status     - Check connect status
GET    /api/payments/connect/dashboard  - Get dashboard link
```

### Service Catalog (`/api/services/*`)
```
GET    /api/services/categories         - List categories
GET    /api/services/categories/{id}    - Category details
GET    /api/services/catalog            - Full service catalog
GET    /api/services/catalog/all-with-instructors - Services with instructors
GET    /api/services/popular            - Popular services
```

### Analytics & Monitoring

#### Search Analytics (`/api/analytics/search/*`)
```
GET    /api/analytics/search/popular-searches - Top searches
GET    /api/analytics/search/conversion-metrics - Conversion rates
GET    /api/analytics/search/search-trends - Trend analysis
GET    /api/analytics/search/search-performance - Performance metrics
```

#### System Monitoring (`/api/monitoring/*`)
```
GET    /api/monitoring/health           - System health check
GET    /api/monitoring/alerts/active    - Active alerts
GET    /api/monitoring/metrics          - System metrics
```

#### Cache Metrics (`/api/metrics/*`)
```
GET    /api/metrics/cache/availability  - Availability cache stats
GET    /api/metrics/cache/performance   - Cache performance
GET    /api/metrics/performance          - API performance metrics
```

## Migration Guide

### For Frontend Developers

#### Update Availability Endpoints
```javascript
// OLD
const response = await fetch('/instructors/availability-windows/week');

// NEW
const response = await fetch('/instructors/availability/week');
```

#### Update Account Management
```javascript
// OLD
const response = await fetch(`/instructors/${instructorId}/suspend`, {
  method: 'POST'
});

// NEW
const response = await fetch('/api/account/suspend', {
  method: 'POST'
});
```

#### Update Booking Completion
```javascript
// OLD - Ambiguous endpoint location
const response = await fetch(`/bookings/${bookingId}/complete`, {
  method: 'POST'
});

// NEW - Clear separation
// For instructors marking lesson complete:
const response = await fetch(`/instructors/bookings/${bookingId}/complete`, {
  method: 'POST'
});

// For system/admin marking complete:
const response = await fetch(`/bookings/${bookingId}/complete`, {
  method: 'POST'
});
```

### For Backend Developers

#### Router Organization
```python
# app/routes/instructors.py
router = APIRouter(prefix="/instructors", tags=["instructors"])

# Public endpoints
@router.get("/")
@router.get("/{instructor_id}")
@router.get("/{instructor_id}/coverage")

# Profile management (authenticated instructor)
@router.post("/me")
@router.get("/me")
@router.put("/me")
@router.delete("/me")

# app/routes/availability.py
router = APIRouter(prefix="/instructors/availability", tags=["availability"])

# app/routes/instructor_bookings.py
router = APIRouter(prefix="/instructors/bookings", tags=["instructor-bookings"])

# app/routes/account_management.py
router = APIRouter(prefix="/api/account", tags=["account"])
```

## Benefits of New Structure

1. **Consistency**: All endpoints use plural nouns (`/instructors`, `/bookings`, `/favorites`)
2. **Clarity**: Clear separation between public and authenticated endpoints
3. **Scalability**: Modular structure allows easy addition of new features
4. **Discoverability**: Logical grouping makes API easier to explore
5. **Maintainability**: Separated concerns reduce coupling
6. **RESTful**: Follows REST conventions more closely

## Deprecation Timeline

- **Phase 1** (Current): New endpoints available alongside old ones
- **Phase 2** (2 weeks): Old endpoints return deprecation headers
- **Phase 3** (4 weeks): Old endpoints return 301 redirects to new ones
- **Phase 4** (8 weeks): Old endpoints removed

## OpenAPI Specification

The complete OpenAPI 3.0 specification is available at:
- File: `/docs/api/instainstru-openapi.yaml`
- Live Docs: `https://api.instainstru.com/docs`
- ReDoc: `https://api.instainstru.com/redoc`

## Questions or Concerns?

Please reach out to the API team for any questions about these changes.
