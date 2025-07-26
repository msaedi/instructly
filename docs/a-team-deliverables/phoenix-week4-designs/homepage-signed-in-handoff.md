# Logged-In Homepage Design - X-Team Handoff
*Date: July 2025*
*A-Team Design Specification for InstaInstru*

## Overview

This document provides the complete design specification for the logged-in homepage experience. The page adapts based on user state, providing personalized content and quick actions for returning students.

## Key Design Principles

1. **Personalization First**: Content adapts based on booking history
2. **Quick Actions**: Enable rebooking and repeat searches in 1-2 clicks
3. **Visual Login State**: Clear indicators that user is logged in
4. **Mobile Responsive**: Optimized for 60% mobile usage

## Header Specifications

### Desktop Header
```
┌─────────────────────────────────────────────────────────────┐
│  🎹 iNSTAiNSTRU                    My lessons  My account [👤]│
└─────────────────────────────────────────────────────────────┘
```

**Layout:**
- Left side: Logo + "iNSTAiNSTRU" branding
- Right side: "My lessons" | "My account" | User Avatar (circular)

**Notification Badges:**
- **My lessons**: Red dot indicator when instructor messages exist
- **My account**: Red dot indicator when platform messages exist

### Mobile Header
```
┌─────────────────┐
│ 🎹 iNSTAiNSTRU │
│ My lessons  [👤]│
└─────────────────┘
```

**Mobile Adaptations:**
- "My account" text hidden (accessible via avatar tap)
- Notification badges remain visible
- Compact spacing for small screens

## Notification Bar

Appears directly below header. Dismissible with [X] button.

### Content Types
1. **Credits Available**: "You have $25 in credits! Book your next lesson today."
2. **New Instructors**: "New Martial Arts instructors in your area! Book today!"
3. **Personalized Deals**: "20% off Piano lessons this week - based on your searches"
4. **Platform Announcements**: "Holiday schedule updates for next week"

### Visual Design
```
│  📢 [Notification message here]                        [X]  │
```

- Background: Light yellow (#FFF8DC)
- Text: Dark gray (#333)
- Dismiss button: Gray hover state
- Auto-dismisses after user action or manual close

## Page Sections

### 1. Your Upcoming Lessons (Conditional)
*Only shows if user has booked sessions*

```
│  📅 Your Upcoming Lessons                                   │
│  ┌─────────────────┐ ┌─────────────────┐                   │
│  │ Tomorrow 3pm    │ │ Thu Jul 18     │                   │
│  │ Piano           │ │ Spanish        │                   │
│  │ with Sarah C.   │ │ with Carlos M. │                   │
│  │ 📍 Upper West   │ │ 📍 Midtown      │                   │
│  │ [View Details]  │ │ [View Details]  │                   │
│  └─────────────────┘ └─────────────────┘                   │
```

**Card Components:**
- Date and time (prominent)
- Subject name
- Instructor name with "with" prefix
- Location area
- "View Details" button

**Mobile:** Single card visible, horizontal scroll for more

### 2. Hero Section
```
│            Your Next Lesson Awaits                          │
│                                                             │
│     [🔍 What do you want to learn?          ] [Search]     │
```

**Design Notes:**
- Same styling as logged-out homepage
- Placeholder text encourages exploration
- Search button in brand yellow (#FFD700)

### 3. Your Recent Searches
```
│  Your Recent Searches                                       │
│                                                             │
│  [piano lessons under $50] [spanish tutor tomorrow]        │
│  [yoga upper west side]                                     │
```

**Pill Design:**
- Light gray background (#F5F5F5)
- Dark text (#333)
- Hover: Darken background 10%
- Click: Repeat exact search
- Show 3 most recent, actual search terms

### 4A. Book Again Section (If Booking History Exists)
```
│  Book Again                                                 │
│                                                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐ │
│  │ Piano           │ │ Yoga            │ │ Guitar       │ │
│  │ with Sarah C.   │ │ with Emma T.    │ │ with Mike R. │ │
│  │ ⭐ 4.9         │ │ ⭐ 5.0          │ │ ⭐ 4.8       │ │
│  │ $75/hour       │ │ $60/hour        │ │ $65/hour     │ │
│  │ [Book Again]   │ │ [Book Again]    │ │ [Book Again] │ │
│  └─────────────────┘ └─────────────────┘ └──────────────┘ │
```

**Card Contents:**
- Subject name (large)
- "with [Instructor name]"
- Star rating
- Price per hour
- "Book Again" button (brand yellow)

**Behavior:**
- Shows up to 3 most recent unique instructors
- Click opens instructor profile with calendar modal
- Mobile: Horizontal scroll

### 4B. How It Works (If NO Booking History)
```
│                 How It Works                                │
│                                                             │
│     1️⃣               2️⃣               3️⃣                    │
│   Search          Choose          Book                      │
│   Find your       Pick from       Confirm &                 │
│   subject         available       start                     │
│                   instructors     learning                   │
```

**Design:** Same as logged-out homepage

### 5. Available Now in Your Area
```
│  Available Now in Your Area                                 │
│                                                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐ │
│  │ James K.        │ │ Lisa M.         │ │ David P.     │ │
│  │ Martial Arts    │ │ French          │ │ Math Tutor   │ │
│  │ ⭐ 4.7         │ │ ⭐ 4.9          │ │ ⭐ 5.0       │ │
│  │ Today 5pm      │ │ Today 4pm       │ │ Today 7pm    │ │
│  │ [Book Now]     │ │ [Book Now]      │ │ [Book Now]   │ │
│  └─────────────────┘ └─────────────────┘ └──────────────┘ │
```

**Updates from logged-out:**
- May show instructors based on past booking areas
- Prioritize subjects similar to booking history

## Responsive Behavior

### Tablet (768px - 1023px)
- 2 cards per row for all sections
- Full header maintained

### Mobile (320px - 767px)
- Single column layout
- Horizontal scroll for card sections
- Show scroll indicators
- "My account" text hidden in header

## States & Variations

### New User (First Login)
- Welcome message in notification bar
- "How It Works" instead of "Book Again"
- Generic area-based recommendations

### Returning User
- Personalized notification content
- "Book Again" section prominent
- Recommendations based on history

### User with Credits
- Credit balance shown in notification bar
- Example: "You have $25 in credits! Book your next lesson today."

### Empty States
- No upcoming lessons: Section hidden entirely
- No recent searches: Show "Start exploring!" message
- No booking history: Show "How It Works"

## Visual Styling Guidelines

### Colors
- Primary Yellow: #FFD700 (buttons, CTAs)
- Text Primary: #333333
- Text Secondary: #666666
- Card Background: #FFFFFF
- Page Background: #F8F8F8
- Notification Bar: #FFF8DC

### Typography
- Headers: 24px, bold
- Card Titles: 18px, medium
- Body Text: 16px, regular
- Mobile: -2px from desktop sizes

### Spacing
- Section Padding: 40px vertical, 24px horizontal
- Card Gaps: 16px
- Mobile Padding: 16px all sides

### Shadows & Borders
- Cards: 1px solid #E0E0E0, 8px border-radius
- Hover: 0 2px 8px rgba(0,0,0,0.1)
- Buttons: No border, rely on color

## Interaction Patterns

1. **Notification Bar**
   - Slides down on page load
   - Dismiss with X button
   - Reappears with new content after 24 hours

2. **Recent Searches**
   - Click pill → Execute same search
   - Pills update after each new search
   - Maximum 3 shown

3. **Book Again**
   - Click card → Instructor profile with calendar modal
   - Preserves last booked service selection

4. **Navigation**
   - "My lessons" → My lessons page
   - "My account" → Account settings
   - Avatar → Account dropdown menu

## Content Guidelines

### Notification Messages
- Keep under 60 characters
- Action-oriented language
- One clear CTA per message
- Rotate content based on user behavior

### Card Content
- Instructor names: First name + last initial
- Times: Use "Today", "Tomorrow" when applicable
- Prices: Always show per hour
- Ratings: One decimal place (4.9, not 4.87)

## Handoff Notes

1. **Conditional Rendering**: Page sections appear/hide based on user data
2. **Notification System**: Requires checking for platform messages, instructor messages, and credits
3. **Responsive Priority**: Mobile experience is primary (60% of users)
4. **Performance**: Cards should load progressively, not all at once
5. **Analytics Events**: Track clicks on "Book Again", recent searches, and notification interactions

---

This completes the logged-in homepage design specification. The page should feel personalized and enable quick rebooking while maintaining the clean, instant-booking experience of InstaInstru.
