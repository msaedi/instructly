# Instructor Profile Page Design Specifications

## Purpose
Enable students to evaluate instructors and quickly book lessons with confidence. This page builds trust, shows availability, and facilitates instant booking within 1-2 clicks.

## User Context
Students arrive here after:
- Clicking instructor card from search results
- Following a direct link/recommendation
- Viewing from their booking history
They've already chosen WHAT to learn, now choosing WHO teaches them.

## Mobile Layout (PRIMARY - 60% of users)

```
[< Back to Results]               [♡ Save]

[●] Sarah Chen
    ⭐ 4.9 (127 reviews)
    📍 Upper West Side

[==== Profile Photo ====]
    🎵 Piano Instructor
    ✓ Background Checked

[Book Now - From $75/hr] ← Sticky button

────────────────────────

📚 About
6 years teaching | Juilliard trained
"Patient and encouraging teacher who
makes learning fun for all ages..."
[Read more]

────────────────────────

💼 Services Offered

┌─────────────────────┐
│ 🎹 Piano Lessons   │
│ 30 min · $75       │
│ Perfect for begin.. │
└─────────────────────┘

┌─────────────────────┐
│ 🎼 Music Theory    │
│ 60 min · $120      │
│ Comprehensive...    │
└─────────────────────┘

────────────────────────

📅 Availability This Week

Mon 28  [10am][2pm][4pm]
Tue 29  [9am][11am][3pm]
Wed 30  Fully Booked
Thu 31  [10am][1pm][5pm]
Fri 1   [9am][2pm]

[View Full Calendar →]

────────────────────────

⭐ Reviews (127)        [See All →]

★★★★★ "Amazing teacher!"
Sarah helped my daughter...
- Emma J., 2 days ago

★★★★★ "Highly recommend"
Very patient and knowle...
- Michael R., 1 week ago

────────────────────────

📍 Location
Upper West Side, NYC
"Near 72nd St subway"

📋 Qualifications
• B.M. Piano Performance, Juilliard
• 6 years teaching experience
• Background check verified ✓

❓ Policies
• Free cancellation up to 24hrs
• First lesson satisfaction guarantee
• In-person lessons only

[Book Now - From $75/hr] ← Sticky
```

## Desktop Layout

```
[← Back to Piano Instructors]                          [♡ Save Instructor]

┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  [Photo]   Sarah Chen                          [Book Now]           │
│            ⭐ 4.9 (127 reviews) · 📍 Upper West Side               │
│            🎵 Piano & Music Theory · ✓ Background Checked          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────┬───────────────────────────┬───────────────────┐
│ About          │ Availability              │ Location          │
├─────────────────┼───────────────────────────┼───────────────────┤
│ 6 years of     │ ┌─ This Week ─┐ ┌─Next─┐ │ 📍 Upper West    │
│ experience     │ │ Mon 28: ▢ ▢ ▢ ▢ ▢ ▢    │ │    Side, NYC   │
│                │ │ Tue 29: ▢ ▢ ▢ ▢ ▢ ▢    │ │                 │
│ Juilliard      │ │ Wed 30: Fully Booked    │ │ "Walking dist.  │
│ trained        │ │ Thu 31: ▢ ▢ ▢ ▢ ▢ ▢    │ │  from 72nd St"  │
│                │ │ Fri 1:  ▢ ▢ ▢ ▢ ▢ ▢    │ │                 │
│ "I believe...  │ │                         │ │ [View Map]      │
│ [Read more]    │ │ ▢ = Available           │ │                 │
│                │ └───────────────────────────┘ │                 │
├─────────────────┴───────────────────────────┴───────────────────┤
│ Skills and pricing                                               │
├──────────────────────────────────────────────────────────────────┤
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐       │
│ │ 🎹 Piano       │ │ 🎹 Piano       │ │ 🎼 Theory      │       │
│ │ Beginner       │ │ Intermediate   │ │ All Levels     │       │
│ │ 30 min · $75   │ │ 45 min · $95   │ │ 60 min · $120  │       │
│ │ [Book This]    │ │ [Book This]    │ │ [Book This]    │       │
│ └────────────────┘ └────────────────┘ └────────────────┘       │
├──────────────────────────────────────────────────────────────────┤
│ Reviews (127)                                    [Write Review]  │
├──────────────────────────────────────────────────────────────────┤
│ ★★★★★ Emma J. · 2 days ago                                      │
│ "Sarah is amazing with kids! My daughter looks forward..."      │
│                                                                  │
│ ★★★★★ Michael R. · 1 week ago                                   │
│ "Very knowledgeable and patient. Helped me prepare for..."      │
│ [Load More Reviews]                                              │
└──────────────────────────────────────────────────────────────────┘
```

## Key Elements

### Header Section
- **Back Navigation**: Context-aware (back to search/category)
- **Save/Favorite**: For quick access later
- **Name & verification badges**: Build immediate trust
- **Rating summary**: Social proof above fold
- **Location**: High-level area info
- **Primary CTA**: Sticky "Book Now" on mobile

### About Section
- **Years experience**: Credibility indicator
- **Education/Training**: Relevant credentials
- **Teaching philosophy**: Personal connection
- **Expandable text**: Progressive disclosure

### Services Offered
- **Service cards**: Visual separation
- **Duration & pricing**: Transparent info
- **Brief description**: Value proposition
- **Direct booking**: One-click from card

### Availability Display
- **This week focus**: Immediate booking intent
- **Time slots**: Simplified view (not specific times)
- **Visual indicators**: Available/booked status
- **Full calendar link**: For planning ahead

### Reviews Section
- **Total count**: Social proof
- **Recent reviews**: Fresh content
- **Star ratings**: Visual scanning
- **Load more**: Performance optimization

### Additional Info
- **Location details**: Neighborhood and landmarks
- **Qualifications**: Credentials list
- **Policies**: Cancellation, guarantees
- **Verification badges**: Safety indicators

## States to Handle

### Default State
- Full content as shown above

### Loading State
```
[Skeleton loader for profile]
[Skeleton cards for services]
[Skeleton blocks for availability]
```

### No Availability State
```
📅 No availability this week
The instructor's calendar is currently full.
[Contact instructor] [Join waitlist]
```

### Error State
```
Unable to load instructor profile
[Try again] [Back to search]
```

## Interaction Design

### Booking Flow
1. **Service Selection**: Click service card or "Book Now"
2. **Calendar Modal**: Shows full availability
3. **Time Selection**: Pick specific slot
4. **Confirmation**: Payment and details

### Save/Favorite
- Toggle heart icon fills/unfills
- Saved instructors appear in user profile
- Optional notification for new availability

### Review Interaction
- "See All" opens full review page
- Can filter by rating/recency
- Only past students can write reviews

### Mobile Gestures
- Swipe between service cards
- Pull to refresh availability
- Tap to expand text sections
- Pinch to zoom profile photo

## Content Guidelines

### Profile Photo
- Professional headshot preferred
- 1:1 aspect ratio
- Minimum 400x400px
- Fallback to initials avatar

### About Text
- 50-200 words
- First person voice
- Focus on teaching approach
- Include relevant experience

### Service Descriptions
- 10-20 words per service
- Clear value proposition
- Skill level indicators
- Action-oriented language

### Reviews Display
- Show 2-3 most recent
- Include reviewer first name + last initial
- Relative timestamps
- Truncate at 2 lines

## Performance Considerations

### Initial Load
- Profile header and photo first
- Service cards next
- Availability lazy loaded
- Reviews loaded on scroll

### Caching Strategy
- Cache instructor data 5 minutes
- Availability refreshed on focus
- Reviews cached 30 minutes
- Service info cached 1 hour

### Mobile Optimizations
- Compress images for mobile
- Lazy load below-fold content
- Minimize JavaScript bundle
- Offline support for viewed profiles

## Accessibility Requirements

### Screen Readers
- Semantic HTML structure
- ARIA labels for icons
- Alt text for images
- Focus management in modals

### Keyboard Navigation
- Tab through all interactive elements
- Enter/Space activate buttons
- Escape closes modals
- Arrow keys navigate calendar

### Visual Accessibility
- High contrast text (4.5:1 minimum)
- Focus indicators visible
- Color not sole indicator
- Scalable text up to 200%

## Analytics Events

Track these user interactions:
- Profile view (with source)
- Service card clicks
- Book Now clicks
- Save/unsave actions
- Review interactions
- Availability calendar opens
- Booking completions
- Back navigation usage

## Edge Cases

### Multiple Services
- Maximum 6 services shown
- "See all services" for more
- Most popular displayed first

### Long Names
- Truncate at 30 characters
- Full name in page title
- Consider mobile width

### No Reviews Yet
```
⭐ New instructor
Be the first to review!
```

### Fully Booked
- Gray out Book Now button
- Show "Join waitlist" option
- Display next available date
