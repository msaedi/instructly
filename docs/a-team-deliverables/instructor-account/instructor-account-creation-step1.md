# Instructor Account Creation - Step 1

## Modal: Initial Registration

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                   X │
│                                                                     │
│                         iNSTAiNSTRU                                 │
│                                                                     │
│        Enter your name as it appears on your government-issued ID   │
│                                                                     │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐  │
│  │ First name                  │  │ Last name                   │  │
│  └─────────────────────────────┘  └─────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Email                                                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Phone number                                                 │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Zipcode                                                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Password                                                 👁️  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Confirm password                                        👁️  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ☐ I agree to the Terms of Service and Privacy Policy             │
│                                                                     │
│              ┌─────────────────────────────────┐                   │
│              │    Create Instructor Account     │                   │
│              └─────────────────────────────────┘                   │
│                                                                     │
│                   Already have an account? Log in                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

[Semi-transparent dark overlay behind modal]
```

## Why We Collect This Information

- **Government ID Name**: Required for background checks and payment processing
- **Phone Number**: For urgent booking notifications and verification
- **Zipcode**: To match instructors with students in their area
- **Email**: Primary communication and account access

## Design Specifications

### Modal Properties
- **Width**: 480px (desktop), 90% (mobile)
- **Padding**: 40px (desktop), 24px (mobile)
- **Background**: White (#FFFFFF)
- **Shadow**: 0 20px 25px rgba(0,0,0,0.15)
- **Border radius**: 12px
- **Overlay**: rgba(0,0,0,0.5)

### Typography
- **Header (iNSTAiNSTRU)**: 28px, bold, brand color
- **Sub-header**: 16px, #4B5563 (gray-600), centered
- **Field labels**: 14px, #374151 (gray-700)
- **Input text**: 16px, #111827 (gray-900)
- **Link text**: 14px, brand color, underline on hover

### Input Fields
- **Height**: 48px
- **Border**: 1px solid #E5E5E5
- **Border radius**: 6px
- **Padding**: 12px 16px
- **Focus state**: Blue border (#3B82F6) with 0 0 0 3px rgba(59,130,246,0.1) shadow
- **Error state**: Red border (#EF4444) with error message below
- **Success state**: Green checkmark inside field

### Special Field Behaviors
- **Phone Number**:
  - Placeholder: "(555) 555-5555"
  - Auto-formatting as user types
  - Only accepts numbers
  - Shows country code +1 on left (grayed out)
- **Zipcode**:
  - Placeholder: "10001"
  - Max length: 5 characters
  - Numbers only
  - Shows "NYC area only" helper text below

### Field Layout
- **First/Last name**:
  - Desktop: Side by side with 16px gap
  - Mobile: Stacked with 16px vertical spacing
- **All fields**: 16px vertical spacing between rows

### Password Fields
- **Show/Hide toggle**:
  - Icon: 👁️ / 👁️‍🗨️
  - Position: Right side, 12px from edge
  - Size: 20px
  - Color: #6B7280 (gray-500)
  - Hover: #374151 (gray-700)

### Checkbox
- **Size**: 20px × 20px
- **Border**: 2px solid #D1D5DB (gray-300)
- **Checked**: Brand color background with white checkmark
- **Label**: 14px, #4B5563 (gray-600)
- **Links**: Brand color, underline on hover

### Button
- **Height**: 48px
- **Width**: 100%
- **Background**: Brand primary color
- **Text**: White, 16px, medium weight (500)
- **Border radius**: 6px
- **Hover**: Darken by 10%
- **Disabled**: #9CA3AF (gray-400) background
- **Enabled when**: All fields valid + terms accepted

### Validation Rules
1. **First name**: Required, 2+ characters, letters only
2. **Last name**: Required, 2+ characters, letters only
3. **Email**: Required, valid email format
4. **Phone number**:
   - Required
   - Format: (XXX) XXX-XXXX
   - Auto-format as user types
   - Must be valid US number
5. **Zipcode**:
   - Required
   - 5 digits
   - Must be valid NYC area zipcode
   - Auto-validate against NYC zipcodes
6. **Password**:
   - Minimum 8 characters
   - At least 1 uppercase letter
   - At least 1 lowercase letter
   - At least 1 number
   - At least 1 special character
7. **Confirm password**: Must match password
8. **Terms**: Must be checked

### Interaction States
- **Loading**: Button shows spinner, fields disabled
- **Success**: Redirect to step 2
- **Error**: Show error message below relevant field
- **Network error**: Toast notification at top

### Mobile Considerations
- **Modal**: Full screen on mobile
- **All input fields**: Stack vertically with consistent spacing
- **Phone number**: Full width with +1 prefix
- **Keyboard**:
  - Email: Email keyboard
  - Phone: Numeric keyboard
  - Zipcode: Numeric keyboard
- **Spacing**: Slightly reduced padding
- **Close button**: Larger tap target (44px × 44px)

### Accessibility
- **Tab order**: Logical flow through all fields
- **ARIA labels**: On all inputs
- **Error announcements**: Screen reader friendly
- **Focus indicators**: Visible for keyboard navigation
- **Password toggle**: Keyboard accessible

## Design Notes

- **Modal Height**: With additional fields, ensure modal is scrollable on smaller screens
- **Field Order**: Contact info (email, phone) grouped together, followed by location (zipcode)
- **Progressive Disclosure**: Consider if all fields needed in step 1 or if some can move to step 2
- **Loading States**: Zipcode validation might need async check for NYC area
