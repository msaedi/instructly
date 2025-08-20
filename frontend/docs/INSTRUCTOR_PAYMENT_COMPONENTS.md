# Instructor Payment Components Documentation

## Overview
This document describes the Stripe Connect onboarding and payouts dashboard components for instructors in the InstaInstru platform.

## Components

### 1. StripeOnboarding Component
**Location:** `/components/instructor/StripeOnboarding.tsx`

**Purpose:** Manages the Stripe Connect onboarding flow for instructors to receive payments.

**Features:**
- Display current onboarding status
- Start new onboarding for unconnected accounts
- Continue incomplete onboarding
- Access Stripe Express dashboard for connected accounts
- Automatic status polling after redirect from Stripe
- Clear status indicators with requirements list

**Props:**
```typescript
interface StripeOnboardingProps {
  instructorId: string;
}
```

**States:**
1. **Not Connected:** Shows "Connect Stripe Account" with requirements list
2. **Onboarding Incomplete:** Shows remaining requirements and "Continue Setup"
3. **Onboarding Complete:** Shows success state with dashboard access
4. **Polling:** Auto-refreshes status when returning from Stripe
5. **Error:** Shows error message with retry option

**Polling Logic:**
- Triggered by `?stripe_onboarding_return=true` URL parameter
- Polls every 2 seconds for up to 30 seconds (15 attempts)
- Automatically stops when onboarding is complete
- Cleans up URL parameters after completion

**Usage:**
```tsx
import StripeOnboarding from '@/components/instructor/StripeOnboarding';

// In your instructor dashboard
<StripeOnboarding instructorId={instructor.id} />
```

### 2. PayoutsDashboard Component
**Location:** `/components/instructor/PayoutsDashboard.tsx`

**Purpose:** Displays earnings summary and provides quick access to payout management.

**Features:**
- Earnings overview cards (total, bookings, fees)
- Quick action buttons for common tasks
- Payout schedule information
- Platform fee disclosure (15%)
- Support contact information

**Props:**
```typescript
interface PayoutsDashboardProps {
  instructorId: string;
}
```

**Data Display:**
- **Total Earnings:** Amount earned after platform fees
- **Total Bookings:** Number of completed sessions
- **Platform Fees:** 15% service fee total
- **Average Earning:** Per-session average

**Quick Actions:**
1. View Stripe Dashboard (opens in new tab)
2. Update Banking Info (redirects to Stripe)
3. Tax Documents (access 1099s in Stripe)

**Usage:**
```tsx
import PayoutsDashboard from '@/components/instructor/PayoutsDashboard';

// Show after onboarding is complete
{onboardingStatus?.onboarding_completed && (
  <PayoutsDashboard instructorId={instructor.id} />
)}
```

## Integration Example

Complete instructor dashboard setup:

```tsx
// pages/dashboard/instructor/payments.tsx
'use client';

import { useState, useEffect } from 'react';
import StripeOnboarding from '@/components/instructor/StripeOnboarding';
import PayoutsDashboard from '@/components/instructor/PayoutsDashboard';
import { paymentService } from '@/services/api/payments';

export default function InstructorPaymentsPage({ instructor }) {
  const [isOnboarded, setIsOnboarded] = useState(false);

  useEffect(() => {
    // Check onboarding status
    const checkStatus = async () => {
      try {
        const status = await paymentService.getOnboardingStatus();
        setIsOnboarded(status.onboarding_completed);
      } catch (error) {
        console.error('Error checking status:', error);
      }
    };

    checkStatus();
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Payments & Payouts</h1>

      {/* Always show onboarding component */}
      <StripeOnboarding instructorId={instructor.id} />

      {/* Show dashboard only if onboarded */}
      {isOnboarded && (
        <PayoutsDashboard instructorId={instructor.id} />
      )}
    </div>
  );
}
```

## API Integration

The components use the `paymentService` from `/services/api/payments.ts`:

```typescript
// Onboarding endpoints
paymentService.startOnboarding()      // Start/continue onboarding
paymentService.getOnboardingStatus()  // Check current status
paymentService.getDashboardLink()     // Get Stripe dashboard URL

// Earnings endpoint (currently using mock data)
paymentService.getEarnings()          // Get earnings summary
```

## URL Parameters

### Onboarding Return Handling
When Stripe redirects back to your app after onboarding:
- URL will contain `?stripe_onboarding_return=true`
- Component automatically starts polling for status updates
- Parameter is cleaned up after onboarding completes

Configure return URLs in Stripe:
```
Success: https://your-app.com/dashboard/instructor?stripe_onboarding_return=true
Refresh: https://your-app.com/dashboard/instructor?stripe_onboarding_return=true
```

## Styling

Components use:
- Tailwind CSS for styling
- Lucide React for icons
- Existing UI components (Button, Card)
- Responsive design (mobile-first)
- Loading states with spinners
- Error states with retry options

## Security Considerations

1. **No Sensitive Data:** Components never handle sensitive financial data
2. **Secure Redirects:** All Stripe URLs are obtained from backend
3. **Authentication Required:** Components should be behind auth middleware
4. **HTTPS Only:** Always use HTTPS in production
5. **Token Validation:** Backend validates all requests

## Testing

### Manual Testing Checklist:
- [ ] Connect new Stripe account
- [ ] Handle incomplete onboarding
- [ ] Complete onboarding successfully
- [ ] Access Stripe dashboard
- [ ] View earnings (mock data)
- [ ] Test error states
- [ ] Test polling timeout
- [ ] Mobile responsive design

### Test Mode:
Use Stripe test mode for development:
1. Create test Stripe account
2. Use test business information
3. Complete onboarding in test mode
4. Verify webhook events

## Platform Fee Structure

- **Service Fee:** 15% of each booking
- **Payment Processing:** Included in platform fee
- **Payout Schedule:** Standard 2-day rolling
- **Minimum Payout:** $1.00 (Stripe minimum)

## Support Information

For payment-related issues:
- Email: payments@instainstru.com
- Help Center: /help/payments
- Stripe Support: Available through Express dashboard

## Future Enhancements

1. **Real Earnings Data:** Replace mock data with actual API calls
2. **Earnings Charts:** Add visual representations of earnings trends
3. **Payout History:** Show recent payouts with status
4. **Instant Payouts:** Option for faster payouts (with fee)
5. **Tax Calculator:** Estimate tax obligations
6. **Export Data:** Download earnings reports as CSV/PDF

## Troubleshooting

### Common Issues:

**Onboarding not completing:**
- Ensure all required fields are filled in Stripe
- Check for verification requirements
- May take 24-48 hours for identity verification

**Dashboard link not working:**
- Links expire after 5 minutes
- Generate new link by clicking button again
- Ensure popup blockers are disabled

**Polling timeout:**
- Manually refresh the page
- Check onboarding status in Stripe directly
- Contact support if issue persists

**No earnings showing:**
- Currently using mock data
- Real data integration coming soon
- Check Stripe dashboard for actual earnings
