# InstaInstru Home Screen - Detailed Sketch

## Mobile View (iPhone 14 Pro dimensions)

```
┌─────────────────────────────────────┐
│  ≡                              9:41 │
│ 📍 NYC - Midtown          👤 Sign in│
├─────────────────────────────────────┤
│                                     │
│      InstaInstru                    │
│   Learn anything, instantly         │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 🔍 What do you need help with? │ │
│ │                                 │ │
│ │ Try: "Piano lesson today"      │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ⚡ Available Right Now              │
│ ┌─────────┬─────────┬─────────┐   │
│ │  Piano  │ Guitar  │  Math   │   │
│ │   🎹    │   🎸    │   📐    │   │
│ │ 12 avail│ 8 avail │ 15 avail│   │
│ │ from $65│ from $45│ from $40│   │
│ └─────────┴─────────┴─────────┘   │
│ ┌─────────┬─────────┬─────────┐   │
│ │ Spanish │ Coding  │  Yoga   │   │
│ │   🗣️    │   💻    │   🧘    │   │
│ │ 6 avail │ 9 avail │ 4 avail │   │
│ │ from $50│ from $70│ from $60│   │
│ └─────────┴─────────┴─────────┘   │
│                                     │
│ 🔥 Trending in Your Area           │
│ ┌─────────────────────────────────┐ │
│ │ • LSAT Prep (38 booked today)  │ │
│ │ • Spanish (35 booked today)    │ │
│ │ • Piano (31 booked today)      │ │
│ │ • Full-Stack Dev (28 booked)   │ │
│ └─────────────────────────────────┘ │
│                                     │
│ 🔄 Book Again                      │
│ ┌─────────────────────────────────┐ │
│ │ Sarah Chen • Piano              │ │
│ │ ⭐ 5.0 • Last: June 28         │ │
│ │ [Book Same Time] [View Times]  │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ────────────────────────────────── │
│  🏠        🔍        📅        👤  │
│  Home    Search   Bookings  Profile│
└─────────────────────────────────────┘
```

## Interaction States

### Search Bar - Focused State
```
┌─────────────────────────────────────┐
│ ┌─────────────────────────────────┐ │
│ │ 🔍 Piano lessons near me|       │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Suggestions:                        │
│ ├─ "Piano lessons today"           │
│ ├─ "Piano lessons this week"       │
│ ├─ "Piano teachers under $70"      │
│ └─ "Piano near Union Square"       │
└─────────────────────────────────────┘
```

### Available Now - Expanded
```
┌─────────────────────────────────────┐
│ ⚡ Available Right Now    [See all] │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Piano (12 instructors)          │ │
│ ├─────────────────────────────────┤ │
│ │ Sarah C. • $75 • 0.8 mi        │ │
│ │ ⭐4.9 • Next: 2:00 PM          │ │
│ │ [Book 2pm] [Book 3pm] [More]   │ │
│ ├─────────────────────────────────┤ │
│ │ Mike R. • $65 • 1.2 mi         │ │
│ │ ⭐4.8 • Next: 5:00 PM          │ │
│ │ [Book 5pm] [Book 6pm] [More]   │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## Design Specifications

### Colors
- **Primary Blue**: #0066CC (CTAs, links)
- **Accent Yellow**: #FFD700 (Available now)
- **Success Green**: #00A86B (Availability)
- **Text Primary**: #1A1A1A
- **Text Secondary**: #666666
- **Background**: #FFFFFF
- **Cards**: #F8F9FA

### Typography
- **App Name**: SF Pro Display Bold 24pt
- **Tagline**: SF Pro Text Regular 16pt
- **Section Headers**: SF Pro Text Semibold 18pt
- **Body**: SF Pro Text Regular 16pt
- **Small Text**: SF Pro Text Regular 14pt

### Spacing
- **Screen Padding**: 16px
- **Section Spacing**: 24px
- **Card Padding**: 12px
- **Button Height**: 44px (Apple HIG)

### Components

#### Search Bar
- Height: 56px
- Border: 1px solid #E0E0E0
- Border Radius: 12px
- Background: #F8F9FA
- Placeholder: #999999

#### Skill Cards
- Size: 110x100px
- Border Radius: 12px
- Shadow: 0 2px 4px rgba(0,0,0,0.1)
- Tap State: Scale 0.95

#### Book Again Card
- Height: 80px
- Background: White
- Border: 1px solid #E0E0E0
- Border Radius: 12px

#### Bottom Navigation
- Height: 80px (includes safe area)
- Background: #FFFFFF
- Border Top: 1px solid #E0E0E0
- Active Color: #0066CC
- Inactive: #999999

## Micro-Interactions

### Search Bar Animation
1. Tap: Border color transitions to blue
2. Keyboard slides up smoothly
3. Suggestions fade in below
4. Recent searches appear if empty

### Skill Card Tap
1. Scale down to 0.95
2. Shadow increases
3. Haptic feedback (light)
4. Navigate to results

### "Book Again" Interaction
1. Swipe left reveals "Remove"
2. Tap "Book Same Time" = instant booking
3. Tap "View Times" = instructor calendar

### Pull to Refresh
1. Location updates
2. Availability refreshes
3. Custom animation (spinning logo)

## Responsive Behavior

### On Scroll
- Search bar stays sticky
- Section headers slide under
- Smooth momentum scrolling
- Parallax on hero text (subtle)

### Landscape Mode
- Cards go 4 across
- Search bar stays prominent
- Hide bottom nav (gesture nav)

### Loading States
- Skeleton screens for cards
- Pulsing animation
- Progressive image loading
- Stagger card appearance

## Accessibility

- **VoiceOver Labels**: All elements labeled
- **Dynamic Type**: Supports system font sizing
- **Color Contrast**: WCAG AA compliant
- **Touch Targets**: Minimum 44x44pt
- **Reduce Motion**: Respects system setting

## Edge Cases

### No Location Permission
```
┌─────────────────────────────────────┐
│ 📍 Enable location for better results│
│        [Enable] [Use NYC]           │
└─────────────────────────────────────┘
```

### First Time User
```
┌─────────────────────────────────────┐
│     Welcome to InstaInstru! 👋      │
│  Book lessons in under 30 seconds   │
│         [How it Works]              │
└─────────────────────────────────────┘
```

### No Internet
```
┌─────────────────────────────────────┐
│    📡 No connection detected        │
│    Check internet and try again     │
│          [Retry]                    │
└─────────────────────────────────────────┘
```
