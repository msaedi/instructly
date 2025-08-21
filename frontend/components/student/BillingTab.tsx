'use client';

import React, { useState, useEffect } from 'react';
import {
  CreditCard,
  Plus,
  Download,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { paymentService, type PaymentMethod } from '@/services/api/payments';
import { format } from 'date-fns';
import { toast } from 'sonner';
import PaymentMethods from '@/components/student/PaymentMethods';

interface BillingTabProps {
  userId: string;
}

interface Transaction {
  id: string;
  service_name: string;
  instructor_name: string;
  booking_date: string;
  duration_minutes: number;
  hourly_rate: number;
  total_price: number;
  platform_fee: number;
  credit_applied: number;
  final_amount: number;
  status: string;
  created_at: string;
}

interface CreditBalance {
  available: number;
  expires_at: string | null;
  pending: number;
}

const BillingTab: React.FC<BillingTabProps> = ({ userId }) => {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [creditBalance, setCreditBalance] = useState<CreditBalance | null>(null);
  const [promoCode, setPromoCode] = useState('');
  const [isLoadingPaymentMethods, setIsLoadingPaymentMethods] = useState(true);
  const [isLoadingTransactions, setIsLoadingTransactions] = useState(true);
  const [isLoadingCredits, setIsLoadingCredits] = useState(true);
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);
  const [showMoreTransactions, setShowMoreTransactions] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load payment methods
  useEffect(() => {
    const loadPaymentMethods = async () => {
      try {
        setIsLoadingPaymentMethods(true);
        const methods = await paymentService.listPaymentMethods();
        setPaymentMethods(methods);
        logger.info('Payment methods loaded', { count: methods.length });
      } catch (err) {
        logger.error('Error loading payment methods:', err);
        setError('Failed to load payment methods');
      } finally {
        setIsLoadingPaymentMethods(false);
      }
    };

    loadPaymentMethods();
  }, [userId]);

  // Load transactions from real API
  useEffect(() => {
    const loadTransactions = async () => {
      try {
        setIsLoadingTransactions(true);
        const data = await paymentService.getTransactionHistory();
        setTransactions(data);
        logger.info('Transactions loaded', { count: data.length });
      } catch (err) {
        logger.error('Error loading transactions:', err);
        // If API fails, don't show error - just show empty state
        setTransactions([]);
      } finally {
        setIsLoadingTransactions(false);
      }
    };

    loadTransactions();
  }, [userId]);

  // Load credit balance from real API
  useEffect(() => {
    const loadCreditBalance = async () => {
      try {
        setIsLoadingCredits(true);
        const data = await paymentService.getCreditBalance();
        setCreditBalance(data);
        logger.info('Credit balance loaded', data);
      } catch (err) {
        logger.error('Error loading credit balance:', err);
        // If API fails, show zero balance
        setCreditBalance({
          available: 0,
          expires_at: null,
          pending: 0,
        });
      } finally {
        setIsLoadingCredits(false);
      }
    };

    loadCreditBalance();
  }, [userId]);

  // Apply promo code
  const handleApplyPromoCode = async () => {
    if (!promoCode.trim()) {
      toast.error('Please enter a promo code');
      return;
    }

    try {
      setIsApplyingPromo(true);
      const result = await paymentService.applyPromoCode(promoCode);

      toast.success(`Promo code applied! $${result.credit_added} added to your balance.`);
      setPromoCode('');

      // Refresh credit balance
      const newBalance = await paymentService.getCreditBalance();
      setCreditBalance(newBalance);
    } catch (err) {
      logger.error('Error applying promo code:', err);
      toast.error('Invalid or expired promo code');
    } finally {
      setIsApplyingPromo(false);
    }
  };

  // Download transaction history
  const handleDownloadHistory = async () => {
    try {
      const blob = await paymentService.downloadTransactionHistory();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transactions_${format(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);

      toast.success('Transaction history downloaded');
    } catch (err) {
      logger.error('Error downloading history:', err);
      toast.error('Failed to download transaction history');
    }
  };

  // Format currency
  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  // Format date
  const formatDate = (dateStr: string): string => {
    try {
      return format(new Date(dateStr), 'MMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="space-y-8">
      {/* Payment Methods Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Payment Methods</h3>
        <PaymentMethods userId={userId} />
      </div>

      <div className="h-px bg-gray-200" />

      {/* Credit Balance Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Credit Balance</h3>

        {isLoadingCredits ? (
          <Card className="p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          </Card>
        ) : creditBalance ? (
          <Card className="p-6 bg-green-50 border-green-200">
            <div className="space-y-2">
              <p className="text-2xl font-bold text-green-900">
                {formatCurrency(creditBalance.available)}
              </p>
              <p className="text-sm text-green-700">Available balance</p>
              {creditBalance.expires_at && (
                <p className="text-xs text-green-600">
                  Expires: {formatDate(creditBalance.expires_at)}
                </p>
              )}
              <p className="text-xs text-gray-600 mt-3">
                *Credits are automatically applied at checkout
              </p>
            </div>
          </Card>
        ) : (
          <Card className="p-6">
            <p className="text-gray-500">No credits available</p>
          </Card>
        )}

        {/* Promo Code Input */}
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Enter promo code:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={promoCode}
              onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
              placeholder="Enter code"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleApplyPromoCode();
                }
              }}
            />
            <Button
              onClick={handleApplyPromoCode}
              disabled={isApplyingPromo || !promoCode.trim()}
            >
              {isApplyingPromo ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Applying...
                </>
              ) : (
                'Apply'
              )}
            </Button>
          </div>
        </div>

        {/* Purchase Credit Package Button */}
        <div className="mt-4">
          <Button
            variant="outline"
            onClick={() => toast.info('Credit packages coming soon!')}
            className="w-full sm:w-auto"
          >
            Purchase Credit Package
          </Button>
        </div>
      </div>

      <div className="h-px bg-gray-200" />

      {/* Transaction History Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Transaction History</h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownloadHistory}
          >
            <Download className="h-4 w-4 mr-2" />
            Download History
          </Button>
        </div>

        {isLoadingTransactions ? (
          <Card className="p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          </Card>
        ) : transactions.length === 0 ? (
          <Card className="p-6">
            <p className="text-gray-500 text-center">No transactions yet</p>
          </Card>
        ) : (
          <div className="space-y-4">
            {transactions.slice(0, showMoreTransactions ? undefined : 5).map((transaction) => (
              <Card key={transaction.id} className="p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h4 className="font-semibold text-gray-900">{transaction.service_name}</h4>
                    <p className="text-sm text-gray-600">{transaction.instructor_name}</p>
                  </div>
                  <p className="text-sm text-gray-500">{formatDate(transaction.booking_date)}</p>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">
                      {formatCurrency(transaction.hourly_rate)}/hr × {transaction.duration_minutes / 60} hr
                    </span>
                    <span className="font-medium">{formatCurrency(transaction.total_price)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Platform Fee</span>
                    <span>{formatCurrency(transaction.platform_fee)}</span>
                  </div>
                  {transaction.credit_applied > 0 && (
                    <div className="flex justify-between">
                      <span className="text-green-600">Credit Applied</span>
                      <span className="text-green-600">-{formatCurrency(transaction.credit_applied)}</span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-gray-200">
                    <div className="flex justify-between">
                      <span className="font-semibold">Total:</span>
                      <span className="font-semibold">{formatCurrency(transaction.final_amount)}</span>
                    </div>
                  </div>
                </div>
              </Card>
            ))}

            {transactions.length > 5 && !showMoreTransactions && (
              <div className="flex justify-center">
                <Button
                  variant="outline"
                  onClick={() => setShowMoreTransactions(true)}
                >
                  Load More Transactions
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-2">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}
    </div>
  );
};

export default BillingTab;
