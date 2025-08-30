'use client';

import React, { useState } from 'react';
import { CreditCard, Plus, Check } from 'lucide-react';
import { PaymentCard, CreditBalance, BookingPayment, PaymentMethod } from '../types';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js';

const stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || '');

// Add Card Form Component - EXACTLY like the billing page
const AddCardFormInner: React.FC<{
  onSuccess: (card: PaymentCard) => void;
  onCancel: () => void;
  cardsLength: number;
}> = ({ onSuccess, onCancel, cardsLength }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setAsDefault, setSetAsDefault] = useState(cardsLength === 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      setError('Card element not found');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Create payment method - EXACTLY like billing page
      const { error: stripeError, paymentMethod } = await stripe.createPaymentMethod({
        type: 'card',
        card: cardElement,
      });

      if (stripeError) {
        setError(stripeError.message || 'Failed to add card');
        setLoading(false);
        return;
      }

      // Save payment method to backend - EXACTLY like billing page
      const savedCard = await paymentService.savePaymentMethod({
        payment_method_id: paymentMethod?.id || '',
        set_as_default: setAsDefault,
      });

      logger.info('Payment method added successfully');

      // Map to PaymentCard type
      const newCard: PaymentCard = {
        id: savedCard.id,
        last4: savedCard.last4,
        brand: savedCard.brand.charAt(0).toUpperCase() + savedCard.brand.slice(1),
        expiryMonth: 12, // Not returned by backend yet
        expiryYear: 2025,
        isDefault: savedCard.is_default,
      };

      onSuccess(newCard);
    } catch (err: any) {
      logger.error('Failed to save payment method', err);
      setError(err.message || 'Failed to save payment method');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <CardElement
        options={{
          style: {
            base: {
              fontSize: '14px',
              color: '#424770',
              '::placeholder': {
                color: '#aab7c4',
              },
            },
          },
        }}
        className="p-2 border border-gray-200 rounded"
      />

      {cardsLength > 0 && (
        <label className="flex items-center text-sm">
          <input
            type="checkbox"
            checked={setAsDefault}
            onChange={(e) => setSetAsDefault(e.target.checked)}
            className="mr-2"
          />
          Set as default payment method
        </label>
      )}

      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!stripe || loading}
          className="flex-1 p-2 bg-purple-700 text-white rounded text-sm hover:bg-purple-800 disabled:bg-gray-300"
        >
          {loading ? 'Adding...' : 'Add Card'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border border-gray-300 rounded text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

interface PaymentMethodSelectionProps {
  booking: BookingPayment;
  cards: PaymentCard[];
  credits: CreditBalance;
  onSelectPayment: (method: PaymentMethod, cardId?: string, creditsToUse?: number) => void;
  onBack?: () => void;
  onCardAdded?: (card: PaymentCard) => void;
}

export default function PaymentMethodSelection({
  booking,
  cards,
  credits,
  onSelectPayment,
  onBack,
  onCardAdded,
}: PaymentMethodSelectionProps) {
  const [selectedCardId, setSelectedCardId] = useState<string>(cards[0]?.id || '');
  const [useCredits, setUseCredits] = useState(false);
  const [creditsToApply, setCreditsToApply] = useState(0);
  const [showNewCardForm, setShowNewCardForm] = useState(false);

  const maxCreditsApplicable = Math.min(credits.totalAmount, booking.totalAmount);
  const remainingAfterCredits = booking.totalAmount - creditsToApply;

  const handleCreditToggle = () => {
    if (!useCredits && credits.totalAmount > 0) {
      setUseCredits(true);
      setCreditsToApply(maxCreditsApplicable);
    } else {
      setUseCredits(false);
      setCreditsToApply(0);
    }
  };

  const handleContinue = () => {
    if (creditsToApply >= booking.totalAmount) {
      onSelectPayment(PaymentMethod.CREDITS, undefined, creditsToApply);
    } else if (creditsToApply > 0) {
      onSelectPayment(PaymentMethod.MIXED, selectedCardId, creditsToApply);
    } else {
      onSelectPayment(PaymentMethod.CREDIT_CARD, selectedCardId);
    }
  };


  // Check if we're in the inline booking flow (from confirmation page)
  const isInlineFlow = !onBack;

  return (
    <div className="p-6">
      <div className="flex gap-6">
        {/* Main Column - 60% width to match confirmation page */}
        <div className="w-[60%] bg-white dark:bg-gray-900 rounded-lg p-6">
          <h3 className="font-extrabold text-2xl mb-4">Select payment method</h3>


          {/* Payment Cards */}
          <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
            <h4 className="font-bold text-xl mb-3">
              {remainingAfterCredits > 0 ? 'Payment Card' : 'Backup Payment Method'}
            </h4>

            <div className="space-y-3">
              {cards.map((card) => (
                <label
                  key={card.id}
                  className={`flex items-center p-3 bg-white border rounded-lg cursor-pointer transition-colors ${
                    selectedCardId === card.id
                      ? 'border-purple-700'
                      : 'border-gray-200'
                  }`}
                >
                  <input
                    type="radio"
                    name="card"
                    value={card.id}
                    checked={selectedCardId === card.id}
                    onChange={(e) => setSelectedCardId(e.target.value)}
                    className="sr-only"
                  />
                  <CreditCard className="mr-3 text-gray-600" size={24} />
                  <div className="flex-1">
                    <p className="text-sm font-medium">
                      {card.brand} ending in {card.last4}
                    </p>
                    {card.isDefault && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded">Default</span>
                    )}
                  </div>
                  {selectedCardId === card.id && <Check className="text-purple-700" size={20} />}
                </label>
              ))}

              {!showNewCardForm ? (
                <button
                  onClick={() => setShowNewCardForm(true)}
                  className="w-full p-3 bg-white border border-dashed border-gray-300 rounded-lg hover:border-purple-700 transition-colors flex items-center justify-center text-sm"
                >
                  <Plus size={18} className="mr-2" />
                  Add New Card
                </button>
              ) : (
                <div className="p-3 bg-white border border-purple-700 rounded-lg">
                  <div className="flex justify-between items-center mb-3">
                    <h5 className="text-sm font-medium">Enter Card Details</h5>
                    <button
                      onClick={() => setShowNewCardForm(false)}
                      className="text-gray-500 hover:text-gray-700"
                    >
                      <Plus size={16} className="rotate-45" />
                    </button>
                  </div>

                  {/* Use Stripe Elements - EXACTLY like billing page */}
                  <Elements stripe={stripePromise}>
                    <AddCardFormInner
                      onSuccess={(newCard) => {
                        // Update UI with new card
                        if (onCardAdded) {
                          onCardAdded(newCard);
                        }
                        // Select the new card
                        setSelectedCardId(newCard.id);
                        // Close form
                        setShowNewCardForm(false);
                        logger.info('Card added and selected', { cardId: newCard.id });
                      }}
                      onCancel={() => setShowNewCardForm(false)}
                      cardsLength={cards.length}
                    />
                  </Elements>
                </div>
              )}
            </div>
          </div>


          {/* Action Button - Single button for inline flow */}
          <div className="mt-6">
            <button
              onClick={handleContinue}
              className="w-full py-2.5 px-4 bg-purple-700 text-white hover:bg-purple-800 rounded-lg font-medium transition-colors focus:outline-none focus:ring-0"
            >
              {isInlineFlow ? 'Apply payment method' : 'Continue to Confirmation'}
            </button>
          </div>

          <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-4">
            🔒 Secure payment • Maximum transaction limit: $1,000
          </p>
        </div>
      </div>
    </div>
  );
}
