# InstaInstru Information Architecture

```
                              InstaInstru
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
    Public/Guest              Authenticated            Admin Panel
        │                         │                    (Future)
        │                         │
        ├── Home                  ├── Student Dashboard
        │   ├── Search Bar        │   ├── Upcoming Lessons
        │   ├── Available Now     │   ├── Past Lessons
        │   ├── Trending Skills   │   ├── Favorite Instructors
        │   └── How It Works      │   ├── Messages
        │                         │   └── Payment Methods
        ├── Search/Browse         │
        │   ├── Search Results    ├── Booking Management
        │   ├── Filters           │   ├── View Booking
        │   │   ├── When         │   ├── Cancel Booking
        │   │   ├── Price        │   ├── Reschedule
        │   │   ├── Location     │   └── Add to Calendar
        │   │   └── Rating       │
        │   └── Map View          ├── Account Settings
        │                         │   ├── Profile Info
        ├── Instructor Profile    │   ├── Preferences
        │   ├── Bio & Creds      │   │   ├── Notifications
        │   ├── Services          │   │   ├── Location
        │   ├── Availability      │   │   └── Language
        │   ├── Reviews           │   ├── Payment Methods
        │   ├── Photos/Videos     │   └── Security
        │   └── Contact           │
        │                         └── Reviews & Ratings
        ├── Booking Flow              ├── Write Review
        │   ├── Select Service         ├── View My Reviews
        │   ├── Choose Time           └── Review History
        │   ├── Add Details
        │   ├── Create Account
        │   └── Payment
        │
        ├── Static Pages
        │   ├── About Us
        │   ├── Trust & Safety
        │   ├── Help/FAQ
        │   ├── Terms
        │   └── Privacy
        │
        └── Auth Flow
            ├── Sign Up
            ├── Log In
            ├── Forgot Password
            └── Social Login

## Data Structure

User
├── Basic Info (name, email, phone)
├── Role (student/instructor/both)
├── Location Preferences
├── Payment Methods
└── Notification Settings

Booking
├── Student Info
├── Instructor Info
├── Service Details
├── Date & Time
├── Location
├── Status
├── Price
└── Messages

Instructor
├── Profile Info
├── Services Offered
├── Availability Schedule
├── Pricing
├── Reviews/Ratings
├── Verification Status
└── Response Time

Service
├── Name
├── Category
├── Duration Options
├── Price
├── Description
└── Requirements

Review
├── Rating (1-5)
├── Text
├── Student Info
├── Booking Reference
└── Instructor Response
```
