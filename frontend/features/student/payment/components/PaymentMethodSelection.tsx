'use client';

import React, { useState, useEffect, useRef } from 'react';
import { CreditCard, Plus, Check, Loader2 } from 'lucide-react';
import { PaymentCard, CreditBalance, BookingPayment, PaymentMethod } from '../types';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js';
import { getStripe, getPaymentElementAppearance } from '@/features/shared/payment/utils/stripe';

// Inner form that uses PaymentElement (must be inside <Elements>)
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

    setLoading(true);
    setError(null);

    try {
      const { error: confirmError, setupIntent } = await stripe.confirmSetup({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/student/booking`,
        },
        redirect: 'if_required',
      });

      if (confirmError) {
        setError(confirmError.message ?? 'Failed to add card');
        setLoading(false);
        return;
      }

      // Save payment method to backend
      let savedCard: PaymentCard | null = null;
      if (setupIntent?.payment_method) {
        const pmId = typeof setupIntent.payment_method === 'string'
          ? setupIntent.payment_method
          : setupIntent.payment_method.id;
        const result = await paymentService.savePaymentMethod({
          payment_method_id: pmId,
          set_as_default: setAsDefault,
        });

        savedCard = {
          id: result.id,
          last4: result.last4,
          brand: result.brand.charAt(0).toUpperCase() + result.brand.slice(1),
          expiryMonth: null,
          expiryYear: null,
          isDefault: result.is_default,
        };
        logger.info('Payment method added successfully');
        onSuccess(savedCard);
      } else {
        setError('Payment method could not be saved. Please try again.');
      }
    } catch (err: unknown) {
      logger.error('Failed to save payment method', err);
      setError(err instanceof Error ? err.message : 'Failed to save payment method');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <PaymentElement
        className="p-2 border border-gray-200 dark:border-gray-700 rounded"
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
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!stripe || loading}
          className="flex-1 p-2 bg-(--color-brand) text-white rounded text-sm hover:bg-purple-800 dark:hover:bg-purple-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 font-semibold"
        >
          {loading ? 'Adding...' : 'Add Card'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

// Wrapper that fetches SetupIntent clientSecret, then renders Elements + inner form
const AddCardFormWrapper: React.FC<{
  onSuccess: (card: PaymentCard) => void;
  onCancel: () => void;
  cardsLength: number;
}> = ({ onSuccess, onCancel, cardsLength }) => {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [intentError, setIntentError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchIntent = async () => {
      try {
        const result = await paymentService.createSetupIntent();
        if (!cancelled) {
          setClientSecret(result.client_secret);
        }
      } catch {
        if (!cancelled) {
          setIntentError('Failed to initialize payment form.');
        }
      }
    };
    void fetchIntent();
    return () => { cancelled = true; };
  }, []);

  if (intentError) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-red-600 dark:text-red-400">{intentError}</p>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded text-sm"
        >
          Cancel
        </button>
      </div>
    );
  }

  if (!clientSecret) {
    return (
      <div className="flex justify-center items-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400 dark:text-gray-300" />
      </div>
    );
  }

  return (
    <Elements
      stripe={getStripe()}
      options={{ clientSecret, appearance: getPaymentElementAppearance(
        typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
      ) }}
    >
      <AddCardFormInner
        onSuccess={onSuccess}
        onCancel={onCancel}
        cardsLength={cardsLength}
      />
    </Elements>
  );
};

interface PaymentMethodSelectionProps {
  booking: BookingPayment;
  cards: PaymentCard[];
  credits: CreditBalance;
  onSelectPayment: (method: PaymentMethod, cardId?: string, creditsToUse?: number) => void;
  onBack?: () => void;
  onCardAdded?: (card: PaymentCard) => void;
  /** When true, renders content only — no outer layout wrapper (for embedding inside another panel) */
  compact?: boolean;
}

export default function PaymentMethodSelection({
  booking,
  cards,
  credits: _credits,
  onSelectPayment,
  onBack,
  onCardAdded,
  compact = false,
}: PaymentMethodSelectionProps) {
  const [selectedCardId, setSelectedCardId] = useState<string>(cards[0]?.id || '');
  const [creditsToApply] = useState(0);
  const [showNewCardForm, setShowNewCardForm] = useState(false);

  const remainingAfterCredits = booking.totalAmount - creditsToApply;


  const handleContinue = () => {
    onSelectPayment(PaymentMethod.CREDIT_CARD, selectedCardId);
  };

  // In compact mode, auto-select the default card on mount (once only)
  const hasAutoSelected = useRef(false);
  useEffect(() => {
    if (compact && selectedCardId && !hasAutoSelected.current) {
      hasAutoSelected.current = true;
      onSelectPayment(PaymentMethod.CREDIT_CARD, selectedCardId);
    }
  }, [compact, selectedCardId, onSelectPayment]);

  // Check if we're in the inline booking flow (from confirmation page)
  const isInlineFlow = !onBack;

  const content = (
    <>
          <h3 className="font-extrabold text-2xl mb-4">Select payment method</h3>


          {/* Payment Cards */}
          <div className="mb-6 rounded-lg p-4 bg-purple-50/60 dark:bg-purple-950/30">
            <h4 className="font-bold text-xl mb-3">
              {remainingAfterCredits > 0 ? 'Payment Card' : 'Backup Payment Method'}
            </h4>

            <div className="space-y-3">
              {cards.map((card) => (
                <label
                  key={card.id}
                  className={`flex items-center p-3 bg-white dark:bg-gray-800 border rounded-lg cursor-pointer transition-colors ${
                    selectedCardId === card.id
                      ? 'border-(--color-brand)'
                      : 'border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="card"
                    value={card.id}
                    checked={selectedCardId === card.id}
                    onChange={(e) => {
                      setSelectedCardId(e.target.value);
                      if (compact) {
                        onSelectPayment(PaymentMethod.CREDIT_CARD, e.target.value);
                      }
                    }}
                    className="sr-only"
                  />
                  <CreditCard className="mr-3 text-gray-600 dark:text-gray-400" size={24} />
                  <div className="flex-1">
                    <p className="text-sm font-medium">
                      {card.brand} ending in {card.last4}
                    </p>
                    {card.isDefault && (
                      <span className="text-xs bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 px-2 py-0.5 rounded">Default</span>
                    )}
                  </div>
                  {selectedCardId === card.id && <Check className="text-(--color-brand)" size={20} />}
                </label>
              ))}

              {!showNewCardForm ? (
                <button
                  onClick={() => setShowNewCardForm(true)}
                  className="w-full p-3 bg-white dark:bg-gray-800 border border-dashed border-gray-300 dark:border-gray-700 rounded-lg hover:border-(--color-brand) transition-colors flex items-center justify-center text-sm"
                >
                  <Plus size={18} className="mr-2" />
                  Add New Card
                </button>
              ) : (
                <div className="p-3 bg-white dark:bg-gray-800 border border-(--color-brand) rounded-lg">
                  <div className="flex justify-between items-center mb-3">
                    <h5 className="text-sm font-medium">Enter Card Details</h5>
                    <button
                      onClick={() => setShowNewCardForm(false)}
                      className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                    >
                      <Plus size={16} className="rotate-45" />
                    </button>
                  </div>

                  <AddCardFormWrapper
                    onSuccess={(newCard) => {
                      if (onCardAdded) {
                        onCardAdded(newCard);
                      }
                      setSelectedCardId(newCard.id);
                      setShowNewCardForm(false);
                      logger.info('Card added and selected', { cardId: newCard.id });
                    }}
                    onCancel={() => setShowNewCardForm(false)}
                    cardsLength={cards.length}
                  />
                </div>
              )}
            </div>
          </div>


          {/* Action Button — hidden in compact mode (card auto-selects, confirm button is below) */}
          {!compact && (
            <>
              <div className="mt-6">
                <button
                  onClick={handleContinue}
                  disabled={!selectedCardId}
                  className="w-full py-2.5 px-4 bg-(--color-brand) text-white hover:bg-purple-800 dark:hover:bg-purple-700 rounded-lg font-medium transition-colors focus:outline-none  disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:text-gray-500 dark:disabled:text-gray-400 disabled:cursor-not-allowed"
                >
                  {isInlineFlow ? 'Apply payment method' : 'Continue to Confirmation'}
                </button>
              </div>

              <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-4">
                🔒 Secure payment • Maximum transaction limit: $1,000
              </p>
            </>
          )}
    </>
  );

  if (compact) {
    return content;
  }

  return (
    <div className="p-6">
      <div className="flex gap-6">
        <div className="w-[60%] bg-white/90 dark:bg-gray-900/70 border border-gray-200/80 dark:border-gray-700/80 rounded-lg p-6">
          {content}
        </div>
      </div>
    </div>
  );
}
