'use client';

import React, { useState, useEffect } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import {
  Elements,
  CardElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import {
  CreditCard,
  Plus,
  Trash2,
  Check,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { paymentService } from '@/services/api/payments';
import DeletePaymentMethodModal from '@/components/modals/DeletePaymentMethodModal';

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || ''
);

interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
  created_at: string;
}

interface PaymentMethodsProps {
  userId: string;
}

// Styled brand names
const getCardBrandDisplay = (brand: string): string => {
  const brandNames: Record<string, string> = {
    visa: 'Visa',
    mastercard: 'Mastercard',
    amex: 'American Express',
    discover: 'Discover',
    diners: 'Diners Club',
    jcb: 'JCB',
    unionpay: 'UnionPay',
    unknown: 'Card',
  };
  return brandNames[brand.toLowerCase()] || brandNames.unknown;
};

// Add Card Form Component
const AddCardForm: React.FC<{
  onSuccess: () => void;
  onCancel: () => void;
}> = ({ onSuccess, onCancel }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveForFuture, setSaveForFuture] = useState(true);
  const [setAsDefault, setSetAsDefault] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    setLoading(true);
    setError(null);

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      setError('Card element not found');
      setLoading(false);
      return;
    }

    try {
      // Create payment method
      const { error: stripeError, paymentMethod } = await stripe.createPaymentMethod({
        type: 'card',
        card: cardElement,
      });

      if (stripeError) {
        setError(stripeError.message || 'Failed to add card');
        setLoading(false);
        return;
      }

      // Save payment method to backend
      await paymentService.savePaymentMethod({
        payment_method_id: paymentMethod?.id || '',
        set_as_default: setAsDefault,
      });

      logger.info('Payment method added successfully');
      onSuccess();
    } catch (err) {
      logger.error('Error adding payment method:', err);
      setError('Failed to add payment method. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="p-4 border rounded-lg">
        <CardElement
          options={{
            style: {
              base: {
                fontSize: '16px',
                color: '#374151',
                fontFamily: 'Inter, system-ui, sans-serif',
                '::placeholder': {
                  color: '#9CA3AF',
                },
              },
              invalid: {
                color: '#EF4444',
                iconColor: '#EF4444',
              },
            },
          }}
        />
      </div>

      <div className="space-y-2">
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={saveForFuture}
            onChange={(e) => setSaveForFuture(e.target.checked)}
            className="rounded border-gray-300"
          />
          <span className="text-sm text-gray-700">Save for future use</span>
        </label>

        {saveForFuture && (
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={setAsDefault}
              onChange={(e) => setSetAsDefault(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">Set as default payment method</span>
          </label>
        )}
      </div>

      {error && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
          <div className="flex items-center space-x-2 text-gray-600 text-sm">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      )}

      <div className="flex space-x-3">
        <Button
          type="submit"
          disabled={loading || !stripe}
          className="flex-1"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Adding...
            </>
          ) : (
            'Add Card'
          )}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={loading}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
};

// Main PaymentMethods Component
const PaymentMethods: React.FC<PaymentMethodsProps> = ({ userId }) => {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [addingCard, setAddingCard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [methodToDelete, setMethodToDelete] = useState<PaymentMethod | null>(null);

  // Load payment methods
  const loadPaymentMethods = async () => {
    try {
      setLoading(true);
      const data = await paymentService.listPaymentMethods();
      setPaymentMethods(data);
      logger.info('Payment methods loaded', { count: data.length });
    } catch (err) {
      logger.error('Error loading payment methods:', err);
      // Don't set error for empty list
      if (err instanceof Error && !err.message.includes('404')) {
        setError('Failed to load payment methods');
      }
    } finally {
      setLoading(false);
    }
  };

  // Set default payment method
  const setDefaultMethod = async (methodId: string) => {
    try {
      await paymentService.setDefaultPaymentMethod(methodId);
      logger.info('Default payment method updated');
      await loadPaymentMethods();
    } catch (err) {
      logger.error('Error setting default payment method:', err);
      setError('Failed to update default payment method');
    }
  };

  // Delete payment method
  const deleteMethod = async () => {
    if (!methodToDelete) return;

    try {
      await paymentService.deletePaymentMethod(methodToDelete.id);
      logger.info('Payment method deleted');
      setDeleteModalOpen(false);
      setMethodToDelete(null);
      await loadPaymentMethods();
    } catch (err) {
      logger.error('Error deleting payment method:', err);
      setError('Failed to delete payment method');
      throw err; // Re-throw to let modal handle the error
    }
  };

  useEffect(() => {
    loadPaymentMethods();
  }, [userId]);

  if (loading) {
    return (
      <div className="flex justify-center items-center py-8">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end items-center">
        {!addingCard && (
          <Button
            onClick={() => setAddingCard(true)}
            className="flex items-center space-x-2 bg-purple-700 hover:bg-purple-800 text-white"
          >
            <Plus className="h-4 w-4" />
            <span>Add Payment Method</span>
          </Button>
        )}
      </div>

      {error && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
          <p className="text-gray-600">{error}</p>
        </div>
      )}

      {addingCard && (
        <div className="rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-medium mb-4">Add New Card</h3>
          <Elements stripe={stripePromise}>
            <AddCardForm
              onSuccess={() => {
                setAddingCard(false);
                loadPaymentMethods();
              }}
              onCancel={() => setAddingCard(false)}
            />
          </Elements>
        </div>
      )}

      {paymentMethods.length === 0 ? (
        <div className="rounded-xl border border-gray-200 p-8 text-center">
          <CreditCard className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            No payment methods saved
          </h3>
          <p className="text-gray-500 mb-4">
            Add a card to make booking faster
          </p>
          {!addingCard && (
            <Button onClick={() => setAddingCard(true)}>
              Add Your First Card
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {paymentMethods.map((method) => (
            <div
              key={method.id}
              className="rounded-xl border border-gray-200 p-4 flex items-center justify-between"
            >
              <div className="flex items-center space-x-4">
                <CreditCard className="h-8 w-8 text-gray-400" />
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">
                      {getCardBrandDisplay(method.brand)}
                    </span>
                    <span className="text-gray-500">•••• {method.last4}</span>
                    {method.is_default && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                        Default
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500">
                    Added {new Date(method.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                {!method.is_default && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setDefaultMethod(method.id)}
                  >
                    Set Default
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setMethodToDelete(method);
                    setDeleteModalOpen(true);
                  }}
                  className="text-red-600 hover:text-red-700"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Payment Method Modal */}
      <DeletePaymentMethodModal
        paymentMethod={methodToDelete}
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setMethodToDelete(null);
        }}
        onConfirm={deleteMethod}
      />
    </div>
  );
};

export default PaymentMethods;
