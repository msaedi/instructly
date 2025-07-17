# InstaInstru Flow Diagrams

This directory contains comprehensive flow diagrams and analysis of the InstaInstru platform's navigation, authentication, and booking systems.

## 📢 Update Notice (July 17, 2025)
Following an independent audit, these diagrams have been updated to correct:
- **Route count**: 66 total (18 frontend + 48 backend API routes)
- **Modal usage**: ValidationPreviewModal, ClearWeekConfirmModal, and ApplyToFutureWeeksModal are actively used
- **Booking auth flow**: Works correctly with proper login redirect
- **Platform completeness**: ~55% overall (95% backend, 45% frontend)
- **Footer links**: 12 broken page links confirmed

See `analysis/audit-corrections.md` for detailed corrections.

## 📊 Available Diagrams

### 1. Student Booking Flow (`student/booking-flow.mmd`)
**Mermaid diagram showing all paths to create a booking**

- **Purpose**: Visualizes every possible way a student can book an instructor
- **Key Insights**:
  - 4 main entry points (Homepage broken, Search, Profile, Direct URL)
  - ALL paths require payment - no booking without payment
  - No guest checkout - authentication required
  - Payment flow uses A-Team's hybrid approach
  - Booking intent preserved through login flow

**View**: Open in any Mermaid-compatible viewer (VS Code, GitHub, etc.)

---

### 2. Navigation Map (`navigation-map.html`)
**Interactive HTML site map of all pages**

- **Purpose**: Complete overview of site structure and navigation paths
- **Features**:
  - Color-coded by access level (Public, Auth, Student, Instructor, Shared)
  - Clickable links show page connections
  - Highlights authentication requirements
  - Shows dynamic route parameters

**View**: Open directly in web browser for interactive experience

---

### 3. Component Usage Analysis (`analysis/component-usage.mmd`)
**Mermaid diagram mapping component reuse across pages**

- **Purpose**: Understand component architecture and identify technical debt
- **Key Findings**:
  - Base Modal component extended by 8 modal types
  - 3 unused modal components (technical debt)
  - Payment components only used within BookingModal
  - Clear separation between shared and page-specific components

**View**: Open in Mermaid viewer to see component relationships

---

### 4. Authentication Flows (`shared/auth-flows.mmd`)
**Mermaid diagram of all authentication patterns**

- **Purpose**: Document login, signup, and protected route handling
- **Covers**:
  - Login/Signup flows with role-based routing
  - Protected route access patterns
  - Dashboard router logic
  - Password reset flow
  - Booking intent preservation
  - Logout process

**View**: Best viewed in Mermaid-compatible editor

---

## 🔍 Key Discoveries

### Critical Issues Found:
1. **No payment bypass** - All bookings require payment (good for business)
2. **Homepage booking broken** - Featured instructors "Book Now" not implemented
3. **2 unused modals** - CancelBookingModal, BookingDetailsModal (others are actively used)
4. **No student profile management** - Users can't edit their information
5. **No saved payment methods** - Must enter card details every time

### Architecture Patterns:
- **Client-side authentication** - No server middleware protection
- **Role-based routing** - Dashboard intelligently routes by user type
- **Component hierarchy** - Clear base → feature component structure
- **Payment integration** - Fully embedded in booking flow

---

## 📝 How to Use These Diagrams

### For Developers:
1. Use booking flow to understand payment integration points
2. Reference navigation map when adding new pages
3. Check component usage before creating new components
4. Follow auth flow patterns for protected routes

### For Product/Design:
1. Review booking flow to identify UX improvements
2. Use navigation map to plan new features
3. Component analysis shows reuse opportunities

### For QA:
1. Test all paths in booking flow
2. Verify auth flows handle edge cases
3. Check navigation paths match implementation

---

## 🛠️ Viewing Tools

### Mermaid Diagrams (.mmd files):
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **GitHub**: Renders automatically in file view
- **Online**: Use [Mermaid Live Editor](https://mermaid.live/)
- **CLI**: `mmdc -i diagram.mmd -o diagram.png` (requires mermaid-cli)

### HTML Files:
- Simply open in any modern web browser
- No special tools required
- Interactive elements work immediately

---

## 📈 Future Improvements

Suggested additions to these diagrams:
1. Instructor onboarding flow
2. Payment processing detailed flow
3. Error handling and recovery paths
4. Mobile vs desktop navigation differences
5. API request/response flow
6. State management diagram

---

Last Updated: 2025-07-17
