'use client';

import React, { useState, useEffect } from 'react';
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import { getStripe, getPaymentElementAppearance } from '@/features/shared/payment/utils/stripe';
import {
  CreditCard,
  Plus,
  Trash2,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { paymentService } from '@/services/api/payments';
import DeletePaymentMethodModal from '@/components/modals/DeletePaymentMethodModal';
import { usePaymentMethods, useInvalidatePaymentMethods } from '@/hooks/queries/usePaymentMethods';

interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
  created_at: string;
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
  return brandNames[brand.toLowerCase()] || brandNames['unknown']!
};

// Inner form that uses PaymentElement (must be inside <Elements>)
const AddCardFormInner: React.FC<{
  onSuccess: () => void;
  onCancel: () => void;
  setAsDefault: boolean;
  setSetAsDefault: (v: boolean) => void;
  showDefaultCheckbox: boolean;
}> = ({ onSuccess, onCancel, setAsDefault, setSetAsDefault, showDefaultCheckbox }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
          return_url: `${window.location.origin}/student/billing`,
        },
        redirect: 'if_required',
      });

      if (confirmError) {
        setError(confirmError.message ?? 'Failed to add payment method');
        setLoading(false);
        return;
      }

      // Save payment method to backend
      if (setupIntent?.payment_method) {
        const pmId = typeof setupIntent.payment_method === 'string'
          ? setupIntent.payment_method
          : setupIntent.payment_method.id;
        await paymentService.savePaymentMethod({
          payment_method_id: pmId,
          set_as_default: setAsDefault,
        });
        logger.info('Payment method added successfully');
        onSuccess();
      } else {
        setError('Payment method could not be saved. Please try again.');
      }
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
        <PaymentElement />
      </div>

      {showDefaultCheckbox && (
        <label className="flex items-center space-x-2">
          <input
            type="checkbox"
            checked={setAsDefault}
            onChange={(e) => setSetAsDefault(e.target.checked)}
            className="rounded border-gray-300 dark:border-gray-700"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">Set as default payment method</span>
        </label>
      )}

      {error && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
          <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400 text-sm">
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
            'Add Payment Method'
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

// Wrapper that fetches SetupIntent clientSecret, then renders Elements + inner form
const AddCardForm: React.FC<{
  onSuccess: () => void;
  onCancel: () => void;
  existingMethodCount: number;
}> = ({ onSuccess, onCancel, existingMethodCount }) => {
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [intentError, setIntentError] = useState<string | null>(null);
  const [setAsDefault, setSetAsDefault] = useState(existingMethodCount === 0);

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
          setIntentError('Failed to initialize payment form. Please try again.');
        }
      }
    };
    void fetchIntent();
    return () => { cancelled = true; };
  }, []);

  if (intentError) {
    return (
      <div className="space-y-4">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
          <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400 text-sm">
            <AlertCircle className="h-4 w-4" />
            <span>{intentError}</span>
          </div>
        </div>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    );
  }

  if (!clientSecret) {
    return (
      <div className="flex justify-center items-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400 dark:text-gray-300" />
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
        setAsDefault={setAsDefault}
        setSetAsDefault={setSetAsDefault}
        showDefaultCheckbox={existingMethodCount > 0}
      />
    </Elements>
  );
};

// Main PaymentMethods Component
const PaymentMethods: React.FC = () => {
  // Use React Query hook for payment methods (prevents duplicate API calls)
  const { data: paymentMethods = [], isLoading: loading, error: queryError } = usePaymentMethods();
  const invalidatePaymentMethods = useInvalidatePaymentMethods();

  const [addingCard, setAddingCard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [methodToDelete, setMethodToDelete] = useState<PaymentMethod | null>(null);

  // Show query error if present
  const displayError = error || (queryError ? 'Failed to load payment methods' : null);

  // Set default payment method
  const setDefaultMethod = async (methodId: string) => {
    try {
      await paymentService.setDefaultPaymentMethod(methodId);
      logger.info('Default payment method updated');
      void invalidatePaymentMethods(); // Refresh data via React Query
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
      void invalidatePaymentMethods(); // Refresh data via React Query
    } catch (err) {
      logger.error('Error deleting payment method:', err);
      setError('Failed to delete payment method');
      throw err; // Re-throw to let modal handle the error
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-8">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400 dark:text-gray-300" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end items-center">
        {!addingCard && (
          <Button
            onClick={() => setAddingCard(true)}
            className="flex items-center space-x-2 bg-[#7E22CE] hover:bg-purple-800 dark:hover:bg-purple-700 text-white"
          >
            <Plus className="h-4 w-4" />
            <span>Add Payment Method</span>
          </Button>
        )}
      </div>

      {displayError && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3">
          <p className="text-gray-600 dark:text-gray-400">{displayError}</p>
        </div>
      )}

      {addingCard && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-medium mb-4">Add New Payment Method</h3>
          <AddCardForm
            onSuccess={() => {
              setAddingCard(false);
              void invalidatePaymentMethods();
            }}
            onCancel={() => setAddingCard(false)}
            existingMethodCount={paymentMethods.length}
          />
        </div>
      )}

      {paymentMethods.length === 0 ? (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center">
          <CreditCard className="h-12 w-12 mx-auto text-gray-400 dark:text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
            No payment methods saved
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
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
              className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between"
            >
              <div className="flex items-center space-x-4">
                <CreditCard className="h-8 w-8 text-gray-400 dark:text-gray-300" />
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-medium">
                      {getCardBrandDisplay(method.brand)}
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">•••• {method.last4}</span>
                    {method.is_default && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200">
                        Default
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
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
                  aria-label={`Delete payment method ending in ${method.last4}`}
                  onClick={() => {
                    setMethodToDelete(method);
                    setDeleteModalOpen(true);
                  }}
                  className="text-red-600 hover:text-red-700 dark:hover:text-red-300"
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
