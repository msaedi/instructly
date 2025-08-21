# Payment Components Documentation

## Overview
This document describes the payment components created for the InstaInstru platform's student payment flow.

## Installation

First, install the required Stripe packages:

```bash
npm install @stripe/stripe-js @stripe/react-stripe-js
```

## Environment Setup

Add your Stripe publishable key to your `.env.local` file:

```env
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key_here
```

## Components

### 1. PaymentMethods Component
**Location:** `/components/student/PaymentMethods.tsx`

**Purpose:** Manages student's saved payment methods

**Features:**
- List all saved payment methods
- Add new payment cards using Stripe Elements
- Set default payment method
- Delete saved cards
- Empty state handling

**Usage:**
```tsx
import PaymentMethods from '@/components/student/PaymentMethods';

// In your component
<PaymentMethods userId={currentUser.id} />
```

### 2. CheckoutFlow Component
**Location:** `/components/booking/CheckoutFlow.tsx`

**Purpose:** Handles the payment process for bookings

**Features:**
- Display booking summary with pricing breakdown
- Select from saved payment methods or add new card
- Process payment with 3D Secure support
- Show platform fees transparently
- Handle success/error states

**Props:**
```typescript
interface CheckoutFlowProps {
  booking: {
    id: string;
    service_name: string;
    instructor_name: string;
    instructor_id: string;
    booking_date: string;
    start_time: string;
    end_time: string;
    duration_minutes: number;
    hourly_rate: number;
    total_price: number;
  };
  onSuccess: (paymentIntentId: string) => void;
  onCancel: () => void;
}
```

**Usage:**
```tsx
import CheckoutFlow from '@/components/booking/CheckoutFlow';

<CheckoutFlow
  booking={bookingData}
  onSuccess={(paymentIntentId) => {
    console.log('Payment successful:', paymentIntentId);
    // Navigate to success page
  }}
  onCancel={() => {
    // Handle cancellation
  }}
/>
```

### 3. BookingModalWithPayment Component
**Location:** `/features/student/booking/components/BookingModalWithPayment.tsx`

**Purpose:** Enhanced booking modal with integrated payment flow

**Features:**
- Multi-step booking process
- Time selection → Booking details → Payment → Success
- Back navigation between steps
- Authentication handling
- Form validation

**Steps:**
1. **Time Selection:** Choose service and view pricing
2. **Booking Details:** Enter contact information
3. **Payment:** Complete payment using CheckoutFlow
4. **Success:** Confirmation message

**Usage:**
Replace your existing BookingModal import:
```tsx
// Before
import BookingModal from '@/features/student/booking/components/BookingModal';

// After
import BookingModalWithPayment from '@/features/student/booking/components/BookingModalWithPayment';

// Use it the same way
<BookingModalWithPayment
  isOpen={isModalOpen}
  onClose={() => setIsModalOpen(false)}
  instructor={instructorData}
  selectedDate={date}
  selectedTime={time}
/>
```

## API Service

**Location:** `/services/api/payments.ts`

The payment service provides all API methods for payment operations:

```typescript
import { paymentService } from '@/services/api/payments';

// List payment methods
const methods = await paymentService.listPaymentMethods();

// Save a new payment method
const newMethod = await paymentService.savePaymentMethod({
  payment_method_id: 'pm_xxx',
  set_as_default: true
});

// Delete a payment method
await paymentService.deletePaymentMethod(methodId);

// Create checkout
const checkout = await paymentService.createCheckout({
  booking_id: bookingId,
  payment_method_id: paymentMethodId,
  save_payment_method: true
});
```

## Test Cards

For development and testing, use these test card numbers:

| Card Type | Number | Description |
|-----------|--------|-------------|
| Success | 4242 4242 4242 4242 | Always succeeds |
| Decline | 4000 0000 0000 0002 | Always declines |
| 3D Secure | 4000 0025 0000 3155 | Requires authentication |
| Insufficient Funds | 4000 0000 0000 9995 | Fails with insufficient funds |

Use any future expiry date and any 3-digit CVV.

## Security Considerations

1. **PCI Compliance:** All components use Stripe Elements, which ensures card data never touches your servers
2. **HTTPS Only:** Always use HTTPS in production
3. **Authentication:** All payment endpoints require user authentication
4. **CVV Re-entry:** For saved cards, users must re-enter CVV for security

## Error Handling

All components include comprehensive error handling:
- Network errors with retry options
- Card validation errors
- 3D Secure authentication failures
- Insufficient funds handling
- Generic error fallbacks

## Styling

Components use Tailwind CSS and follow InstaInstru's design system:
- Consistent spacing and typography
- Mobile responsive
- Loading states with spinners
- Success/error animations
- Accessible form inputs

## Platform Fees

The system automatically calculates and displays:
- Service fee (booking total)
- Platform fee (15% of service fee)
- Total amount charged to student

## Next Steps

1. Configure webhook endpoints for payment status updates
2. Implement email receipts
3. Add refund functionality
4. Set up production Stripe keys
5. Test full payment flow end-to-end

## Support

For issues or questions about the payment components, please refer to:
- [Stripe Documentation](https://stripe.com/docs)
- [Stripe Elements Guide](https://stripe.com/docs/stripe-js)
- [React Stripe.js Reference](https://stripe.com/docs/stripe-js/react)
