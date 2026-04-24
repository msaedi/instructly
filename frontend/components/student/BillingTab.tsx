'use client';

import React, { useEffect, useState } from 'react';
import {
  Download,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { paymentService } from '@/services/api/payments';
import { format } from 'date-fns';
import { toast } from 'sonner';
import PaymentMethods from '@/components/student/PaymentMethods';
import { useCredits } from '@/features/shared/payment/hooks/useCredits';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { useTransactionHistory } from '@/hooks/queries/useTransactionHistory';

interface Transaction {
  id: string;
  service_name: string;
  instructor_name: string;
  booking_date: string;
  duration_minutes: number;
  hourly_rate: number;
  lesson_amount: number;
  service_fee: number;
  credit_applied: number;
  tip_amount: number;
  tip_paid: number;
  tip_status?: string | null;
  total_paid: number;
  status: string;
  created_at: string;
}

const BillingTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [promoCode, setPromoCode] = useState('');
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);
  const [showMoreTransactions, setShowMoreTransactions] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    const syncDarkMode = () => {
      setIsDarkMode(root.classList.contains('dark'));
    };

    syncDarkMode();

    const observer = new MutationObserver(syncDarkMode);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });

    return () => {
      observer.disconnect();
    };
  }, []);

  // Use shared credits hook with React Query
  const { data: creditBalance, isLoading: isLoadingCredits, refetch: refetchCredits } = useCredits();

  // Use React Query hook for transaction history (prevents duplicate API calls)
  const { data: transactionsData, isLoading: isLoadingTransactions } = useTransactionHistory();
  const transactions = (transactionsData ?? []) as Transaction[];

  // Apply promo code
  const handleApplyPromoCode = async () => {
    if (!promoCode.trim()) {
      toast.error('Please enter a promo code', {
        style: {
          background: '#fbbf24',
          color: '#000000',
          border: 'none',
        },
      });
      return;
    }

    try {
      setIsApplyingPromo(true);
      const result = await paymentService.applyPromoCode(promoCode);

      toast.success(`Promo code applied! $${result.credit_added} added to your balance.`);
      setPromoCode('');

      // Refresh credit balance via React Query
      await queryClient.invalidateQueries({ queryKey: queryKeys.payments.credits });
      await refetchCredits();
    } catch (err) {
      logger.error('Error applying promo code:', err);
      toast.error('Invalid or expired promo code', {
        style: {
          background: '#fbbf24',
          color: '#000000',
          border: 'none',
        },
      });
    } finally {
      setIsApplyingPromo(false);
    }
  };

  // Download transaction history
  const handleDownloadHistory = async () => {
    try {
      // Check if there are transactions to download
      if (transactions.length === 0) {
        toast.info('No transactions to download');
        return;
      }

      // For now, create a CSV from the existing transaction data
      const csvContent = [
        ['Date', 'Service', 'Instructor', 'Duration (min)', 'Lesson Amount', 'Service Fee', 'Credit Applied', 'Tip Paid', 'Total Paid', 'Status'],
        ...transactions.map(t => [
          format(new Date(t.booking_date), 'yyyy-MM-dd'),
          t.service_name,
          t.instructor_name,
          t.duration_minutes,
          t.lesson_amount,
          t.service_fee,
          t.credit_applied,
          t.tip_paid,
          t.total_paid,
          t.status
        ])
      ].map(row => row.join(',')).join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `transactions_${format(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);

      toast.success('Transaction history downloaded');
    } catch (err) {
      logger.error('Error downloading history:', err);
      toast.info('Download feature coming soon!');
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

  const creditCardStyle = isDarkMode
    ? {
      borderColor: 'rgba(192, 132, 252, 0.58)',
      backgroundColor: 'rgba(88, 28, 135, 0.22)',
      boxShadow: '0 10px 24px rgba(2, 6, 23, 0.32)',
    }
    : {
      borderColor: 'rgba(216, 180, 254, 0.92)',
      backgroundColor: 'rgba(245, 236, 255, 0.95)',
      boxShadow: '0 8px 18px rgba(126, 34, 206, 0.08)',
    };

  return (
    <div className="space-y-8">
      {/* Payment Methods Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Payment Methods</h3>
        <PaymentMethods />
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700" />

      {/* Credit Balance Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Credit Balance</h3>

        {isLoadingCredits ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400 dark:text-gray-300" />
            </div>
          </div>
        ) : creditBalance && creditBalance.available > 0 ? (
          <div className="rounded-xl border p-6" style={creditCardStyle}>
            <div className="space-y-2">
              <p className="text-2xl font-bold text-(--color-brand)">
                {formatCurrency(creditBalance.available)}
              </p>
              <p className="text-sm text-purple-600 dark:text-purple-200">Available balance</p>
              {creditBalance.expires_at ? (
                <p className="text-xs text-purple-500 dark:text-purple-300">
                  Earliest expiry: {formatDate(creditBalance.expires_at)}
                </p>
              ) : (
                <p className="text-xs text-purple-500 dark:text-purple-300">No expiry on current credits</p>
              )}
              <p className="text-xs text-gray-600 dark:text-gray-300 mt-3">
                *Credits are automatically applied at checkout
              </p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <p className="text-gray-500 dark:text-gray-400">No credits available</p>
          </div>
        )}

        {/* Promo Code Input */}
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Enter promo code:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={promoCode}
              onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
              placeholder="Enter code"
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  void handleApplyPromoCode();
                }
              }}
            />
            <Button
              onClick={() => void handleApplyPromoCode()}
              disabled={isApplyingPromo || !promoCode.trim()}
              className="bg-(--color-brand) hover:bg-purple-800 dark:hover:bg-purple-700 text-white"
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
            className="w-full sm:w-auto border-(--color-brand) text-(--color-brand) hover:bg-purple-50 dark:hover:bg-purple-900/30"
          >
            Purchase Credit Package
          </Button>
        </div>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700" />

      {/* Transaction History Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Transaction History</h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownloadHistory}
            className="text-(--color-brand) hover:text-purple-900 dark:hover:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30"
          >
            <Download className="h-4 w-4 mr-2" />
            Download History
          </Button>
        </div>

        {isLoadingTransactions ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400 dark:text-gray-300" />
            </div>
          </div>
        ) : transactions.length === 0 ? (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
            <p className="text-gray-500 dark:text-gray-400 text-center">No transactions yet</p>
          </div>
        ) : (
          <div className="space-y-4">
            {transactions.slice(0, showMoreTransactions ? undefined : 5).map((transaction) => (
              <div key={transaction.id} className="rounded-xl border border-gray-200 dark:border-gray-700 p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">{transaction.service_name}</h4>
                    <p className="text-sm text-gray-600 dark:text-gray-400">{transaction.instructor_name}</p>
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{formatDate(transaction.booking_date)}</p>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Lesson ({transaction.duration_minutes} min)</span>
                    <span className="font-medium">{formatCurrency(transaction.lesson_amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Platform fee</span>
                    <span>{formatCurrency(transaction.service_fee)}</span>
                  </div>
                  {transaction.credit_applied > 0 && (
                    <div className="flex justify-between">
                      <span className="text-green-600">Credit Applied</span>
                      <span className="text-green-600">-{formatCurrency(transaction.credit_applied)}</span>
                    </div>
                  )}
                  {transaction.tip_amount > 0 && (
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        Tip{transaction.tip_paid < transaction.tip_amount ? ' (pending)' : ''}
                      </span>
                      <span>
                        {formatCurrency(
                          transaction.tip_paid > 0 ? transaction.tip_paid : transaction.tip_amount
                        )}
                      </span>
                    </div>
                  )}
                  <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex justify-between">
                      <span className="font-semibold">Total:</span>
                      <span className="font-semibold">{formatCurrency(transaction.total_paid)}</span>
                    </div>
                  </div>
                  {transaction.tip_paid < transaction.tip_amount && transaction.tip_amount > 0 && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Tip will be charged once payment method is confirmed.
                    </p>
                  )}
                </div>
              </div>
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
    </div>
  );
};

export default BillingTab;
