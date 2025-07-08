# Email Templates

This directory contains Jinja2 templates for all platform emails.

## Structure
- `email/base.html` - Base template with common styling
- `email/booking/` - Booking-related emails
- `email/auth/` - Authentication emails (password reset, welcome)
- `email/components/` - Reusable components

## Usage
Templates are rendered via the `template_service.py` module.

## Variables
All templates have access to:
- `brand_name` - InstaInstru
- `current_year` - Current year
- `frontend_url` - Frontend URL
- Plus any context passed when rendering
