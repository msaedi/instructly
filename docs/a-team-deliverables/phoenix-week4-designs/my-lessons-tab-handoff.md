# My Lessons Flow Design - X-Team Handoff
*Date: July 2025*
*A-Team Design Specification for InstaInstru*

## Overview

This document provides complete design specifications for the My Lessons flow, including lesson management, details, rescheduling, and cancellation. The design prioritizes quick actions and clear information display.

## Design Principles

1. **Quick Actions**: Enable rebooking and management in minimal clicks
2. **Clear Information**: Show all relevant lesson details upfront
3. **Flexible Management**: Easy reschedule/cancel with clear policies
4. **Mobile Responsive**: Optimized for on-the-go lesson management

## Page Specifications

### 1. My Lessons Page - Current/Upcoming Tab (Default)

```
┌─────────────────────────────────────────────────────────────┐
│  🎹 iNSTAiNSTRU                    My lessons  My account [👤]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Current]    Completed                                     │
│  ─────────                                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Piano Lesson                                         │  │
│  │                                                      │  │
│  │ 📅 Wed Mar 5                                        │  │
│  │ 🕐 4:00pm EDT                                       │  │
│  │ 💵 $75.00                                           │  │
│  │                                     See lesson details →│  │
│  │                                                      │  │
│  │ ┌────┐ Sarah Chen                                   │  │
│  │ │    │ ⭐ 4.9 (127 reviews)                         │  │
│  │ │    │ ✓ 68 lessons completed                [Chat] │  │
│  │ └────┘                                              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Spanish Lesson                                       │  │
│  │                                                      │  │
│  │ 📅 Thu Mar 6                                        │  │
│  │ 🕐 10:00am EDT                                      │  │
│  │ 💵 $60.00                                           │  │
│  │                                     See lesson details →│  │
│  │                                                      │  │
│  │ ┌────┐ Carlos Martinez                              │  │
│  │ │    │ ⭐ 4.8 (89 reviews)                          │  │
│  │ │    │ ✓ 156 lessons completed               [Chat] │  │
│  │ └────┘                                              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Card Components:**
- Lesson subject (large, bold)
- Date with day of week
- Time in user's timezone
- Price per lesson
- "See lesson details" link
- Instructor section:
  - Avatar (48x48px)
  - Name
  - Star rating with review count
  - Completed lessons count
  - Chat button

**Empty State:**
```
No upcoming lessons

Ready to learn something new?
[Browse Instructors]
```

### 2. My Lessons Page - Completed Tab

```
┌─────────────────────────────────────────────────────────────┐
│  🎹 iNSTAiNSTRU                    My lessons  My account [👤]│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Current    [Completed]                                     │
│             ───────────                                     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Piano Lesson - COMPLETED                             │  │
│  │                                                      │  │
│  │ 📅 Tue Feb 27, 2024                                 │  │
│  │ 🕐 3:00pm EDT                                       │  │
│  │ 💵 $75.00                                           │  │
│  │                                        [Book Again]  │  │
│  │                                     See lesson details →│  │
│  │                                                      │  │
│  │ ┌────┐ Sarah Chen                                   │  │
│  │ │    │ ⭐ 4.9 (127 reviews)          [Review & tip] │  │
│  │ └────┘ ✓ 68 lessons completed                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Yoga Class - CANCELLED (>24hrs)                      │  │
│  │                                                      │  │
│  │ 📅 Mon Feb 19, 2024                                 │  │
│  │ 🕐 6:00pm EDT                                       │  │
│  │ 💵 $0.00 (No charge)                                │  │
│  │                                        [Book Again]  │  │
│  │                                     See lesson details →│  │
│  │                                                      │  │
│  │ ┌────┐ Emma Thompson                                │  │
│  │ │    │ ⭐ 5.0 (95 reviews)                          │  │
│  │ └────┘ ✓ 112 lessons completed                      │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Guitar Lesson - CANCELLED (12-24hrs)                 │  │
│  │                                                      │  │
│  │ 📅 Sun Feb 11, 2024                                 │  │
│  │ 🕐 2:00pm EDT                                       │  │
│  │ 💵 Charged: $65.00 | Credit: $32.50                 │  │
│  │                                        [Book Again]  │  │
│  │                                     See lesson details →│  │
│  │                                                      │  │
│  │ ┌────┐ Michael Rodriguez                            │  │
│  │ │    │ ⭐ 4.7 (84 reviews)                          │  │
│  │ └────┘ ✓ 92 lessons completed                       │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Status Variations:**
- **COMPLETED**: Shows original price, "Review & tip" button
- **CANCELLED (>24hrs)**: Shows "$0.00 (No charge)"
- **CANCELLED (12-24hrs)**: Shows "Charged: $X | Credit: $X/2"
- **CANCELLED (<12hrs)**: Shows full charge amount
- **Book Again** button added above "See lesson details" for all

### 3. Lesson Details Page - Completed Version

```
┌─────────────────────────────────────────────────────────────┐
│  [← Back to My Lessons]                        View receipt │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Piano Lesson - COMPLETED                                   │
│                                                             │
│  📅 Tue Feb 27, 2024                                       │
│  🕐 3:00pm EDT                                              │
│  💵 $75.00                                                  │
│                                                             │
│  ┌────┐ Sarah Chen                                         │
│  │    │ ⭐ 4.9 (127 reviews)                               │
│  │    │ ✓ 68 lessons completed                             │
│  └────┘                                                    │
│                                                             │
│  [Review & tip]  [Chat history]  [Book Again]              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Lesson Details                                             │
│                                                             │
│  Location                                                   │
│  Upper West Side, NYC                                       │
│  225 W 72nd St, Apt 4B, New York, NY 10023                │
│                                                             │
│  Description                                                │
│  Intermediate piano lesson focusing on classical pieces.    │
│  Working on Mozart Sonata No. 11.                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Receipt                                                    │
│                                                             │
│  Date of Lesson                              Tue Feb 27     │
│  $75.00/hr x 1 hr                              $75.00      │
│  Platform Fee                                   $11.25      │
│  ─────────────────────────────────────────────────────     │
│  Total                                          $86.25      │
│  Paid                                           $86.25      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4. Lesson Details Page - Upcoming Version

```
┌─────────────────────────────────────────────────────────────┐
│  [← Back to My Lessons]                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Piano Lesson                                               │
│                                                             │
│  📅 Wed Mar 5                                              │
│  🕐 4:00pm EDT                                              │
│  💵 $75.00                                                  │
│                                                             │
│  ┌────┐ Sarah Chen                                         │
│  │    │ ⭐ 4.9 (127 reviews)                               │
│  │    │ ✓ 68 lessons completed                             │
│  └────┘                                                    │
│                                                             │
│  [Chat with instructor]                                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Lesson Details                                             │
│                                                             │
│  Location                                                   │
│  Upper West Side, NYC                                       │
│  225 W 72nd St, Apt 4B, New York, NY 10023                │
│  [View map]                                                 │
│                                                             │
│  Description                                                │
│  Intermediate piano lesson focusing on classical pieces.    │
│  Please bring your sheet music for Mozart Sonata No. 11.   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Manage Booking                                             │
│                                                             │
│         [Reschedule lesson]    [Cancel lesson]              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Changes:**
- Full address shown immediately (no 24hr hiding)
- Clear action buttons for reschedule/cancel
- Map link for navigation

## Modal Specifications

### 5. Reschedule Modal - Calendar View (Recommended)

```
┌─────────────────────────────────────────────────┐
│  Need to reschedule?                        [X] │
├─────────────────────────────────────────────────┤
│                                                 │
│  Select a new time with Sarah Chen              │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ March 2024                                │  │
│  │ Mo Tu We Th Fr Sa Su                     │  │
│  │  4  5  6  7  8  9 10                     │  │
│  │    [X] ✓  ✓  ✓  -- --                   │  │
│  │ 11 12 13 14 15 16 17                     │  │
│  │  ✓  ✓  ✓  ✓  ✓  -- --                   │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  Available times on Thu Mar 7:                 │
│  [10:00am] [11:00am] [2:00pm] [3:00pm]        │
│                                                 │
│  Current lesson: Wed Mar 5 at 4:00pm           │
│                                                 │
│       [Confirm reschedule]                      │
│                                                 │
│  Prefer to discuss? [Chat to reschedule]       │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Calendar Key:**
- [X] = Current booking
- ✓ = Available days
- -- = No availability
- Grayed out = Past dates

### 6. Cancel Lesson - Warning Modal

```
┌─────────────────────────────────────────────────┐
│  Cancel lesson                              [X] │
├─────────────────────────────────────────────────┤
│                                                 │
│  ⚠️ Cancellation Policy                         │
│                                                 │
│  Your lesson: Wed Mar 5 at 4:00pm              │
│  Time until lesson: 18 hours                   │
│                                                 │
│  Cancellation fee: $37.50                      │
│  (50% of lesson price)                         │
│                                                 │
│  💡 Avoid the fee by rescheduling instead.     │
│                                                 │
│         [Reschedule lesson]                     │
│                                                 │
│           [Cancel lesson]                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Fee Structure Display:**
- **>24 hours**: "No cancellation fee"
- **12-24 hours**: "$X cancellation fee (50% of lesson)"
- **<12 hours**: "$X cancellation fee (100% of lesson)"

### 7. Cancellation Reason Modal

```
┌─────────────────────────────────────────────────┐
│  Why do you want to cancel?                [X] │
├─────────────────────────────────────────────────┤
│                                                 │
│  Need to reschedule instead? [Reschedule]      │
│                                                 │
│  Still want to cancel? Please let us know why. │
│                                                 │
│  ○ Lesson was booked by mistake                │
│  ○ My schedule changed or conflict             │
│  ○ Instructor's schedule changed               │
│  ○ Found another instructor                    │
│  ○ Instructor cancelled or no-show             │
│  ○ I changed my mind / no longer need          │
│  ○ Emergency or unexpected event               │
│  ○ Other reason                                │
│                                                 │
│  This feedback helps improve InstaInstru.      │
│                                                 │
│              [Continue]                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 8. Cancellation Confirmation Modal

```
┌─────────────────────────────────────────────────┐
│  Your lesson has been cancelled            [X] │
├─────────────────────────────────────────────────┤
│                                                 │
│  ✓ Cancellation confirmed                       │
│                                                 │
│  Lesson: Piano with Sarah Chen                 │
│  Date: Wed Mar 5 at 4:00pm                     │
│                                                 │
│  Cancellation fee: $37.50                      │
│  Credit issued: $37.50                         │
│                                                 │
│  Your credit will be applied to your next      │
│  booking automatically.                         │
│                                                 │
│  Questions? [Contact support]                  │
│                                                 │
│               [Done]                            │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Confirmation Variations:**
- **No fee**: Shows "No cancellation fee" and full refund
- **Partial fee**: Shows fee and credit amount
- **Full fee**: Shows full charge, no credit

## Mobile Responsive Behavior

### Mobile Layout Adjustments
- Single column for all cards
- Instructor info stacked vertically
- Buttons full width
- Modal dialogs: 90% screen width
- Calendar: Scrollable with week view

### Touch Interactions
- Swipe between Current/Completed tabs
- Tap cards for details
- Large touch targets (44px minimum)
- Pull to refresh on lists

## Empty States

### No Current Lessons
```
You don't have any upcoming lessons

Ready to learn something new?
[Find Instructors]
```

### No Completed Lessons
```
No completed lessons yet

Your lesson history will appear here
after your first session.
```

## Navigation Flow

```
My Lessons (Tab Selection)
    ├── Current Tab
    │   └── Lesson Card → Lesson Details
    │       ├── Chat → Messaging
    │       ├── Reschedule → Calendar Modal
    │       └── Cancel → Warning → Reason → Confirmation
    │
    └── Completed Tab
        └── Lesson Card → Lesson Details
            ├── Book Again → Instructor Profile
            ├── Review & Tip → Review Modal
            └── Chat History → Past Messages
```

## Visual Styling

### Status Indicators
- **COMPLETED**: Green accent
- **CANCELLED**: Gray/muted
- **Upcoming**: Default styling

### Buttons
- Primary (yellow): Book Again, Confirm actions
- Secondary (outline): Chat, View details
- Danger (red text): Cancel lesson

### Typography
- Lesson titles: 20px, bold
- Dates/times: 16px, medium
- Body text: 14px, regular
- Mobile: -2px from desktop

## Handoff Notes

1. **Cancellation Logic**: Display different fees based on timing
2. **Book Again**: Should pre-select same service and show calendar
3. **Chat Integration**: Links to messaging system
4. **Mobile Priority**: Optimize for one-handed use
5. **Performance**: Lazy load completed lessons, show skeleton states

---

This completes the My Lessons flow design specification. The design enables quick lesson management while clearly communicating policies and providing multiple paths to avoid cancellation fees.
