'use client';

import React, { useState, useEffect } from 'react';
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
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [creditBalance, setCreditBalance] = useState<CreditBalance | null>(null);
  const [promoCode, setPromoCode] = useState('');
  const [isLoadingTransactions, setIsLoadingTransactions] = useState(true);
  const [isLoadingCredits, setIsLoadingCredits] = useState(true);
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);
  const [showMoreTransactions, setShowMoreTransactions] = useState(false);


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

      toast.success(`Promo code applied! $${result.credit_added} added to your balance.`, {
        style: {
          background: '#6b21a8',
          color: 'white',
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
        },
      });
      setPromoCode('');

      // Refresh credit balance
      const newBalance = await paymentService.getCreditBalance();
      setCreditBalance(newBalance);
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
        toast.info('No transactions to download', {
          style: {
            background: '#6b21a8',
            color: 'white',
            border: 'none',
            boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
          },
        });
        return;
      }

      // For now, create a CSV from the existing transaction data
      const csvContent = [
        ['Date', 'Service', 'Instructor', 'Duration (min)', 'Total Price', 'Platform Fee', 'Credit Applied', 'Final Amount', 'Status'],
        ...transactions.map(t => [
          format(new Date(t.booking_date), 'yyyy-MM-dd'),
          t.service_name,
          t.instructor_name,
          t.duration_minutes,
          t.total_price,
          t.platform_fee,
          t.credit_applied,
          t.final_amount,
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

      toast.success('Transaction history downloaded', {
        style: {
          background: '#6b21a8',
          color: 'white',
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
        },
      });
    } catch (err) {
      logger.error('Error downloading history:', err);
      toast.info('Download feature coming soon!', {
        style: {
          background: '#6b21a8',
          color: 'white',
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
        },
      });
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

      <div className="border-b border-gray-200" />

      {/* Credit Balance Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Credit Balance</h3>

        {isLoadingCredits ? (
          <div className="rounded-xl border border-gray-200 p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          </div>
        ) : creditBalance ? (
          <div className="rounded-xl border border-gray-200 p-6 bg-purple-50">
            <div className="space-y-2">
              <p className="text-2xl font-bold text-purple-700">
                {formatCurrency(creditBalance.available)}
              </p>
              <p className="text-sm text-purple-600">Available balance</p>
              {creditBalance.expires_at ? (
                <p className="text-xs text-purple-500">
                  Earliest expiry: {formatDate(creditBalance.expires_at)}
                </p>
              ) : (
                <p className="text-xs text-purple-500">No expiry on current credits</p>
              )}
              <p className="text-xs text-gray-600 mt-3">
                *Credits are automatically applied at checkout
              </p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 p-6">
            <p className="text-gray-500">No credits available</p>
          </div>
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
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/25 focus:border-purple-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleApplyPromoCode();
                }
              }}
            />
            <Button
              onClick={handleApplyPromoCode}
              disabled={isApplyingPromo || !promoCode.trim()}
              className="bg-purple-700 hover:bg-purple-800 text-white"
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
            onClick={() => toast.info('Credit packages coming soon!', {
              style: {
                background: '#6b21a8',
                color: 'white',
                border: 'none',
                boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
              },
            })}
            className="w-full sm:w-auto border-purple-700 text-purple-700 hover:bg-purple-50"
          >
            Purchase Credit Package
          </Button>
        </div>
      </div>

      <div className="border-b border-gray-200" />

      {/* Transaction History Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Transaction History</h3>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownloadHistory}
            className="text-purple-700 hover:text-purple-800 hover:bg-purple-50"
          >
            <Download className="h-4 w-4 mr-2" />
            Download History
          </Button>
        </div>

        {isLoadingTransactions ? (
          <div className="rounded-xl border border-gray-200 p-6">
            <div className="flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            </div>
          </div>
        ) : transactions.length === 0 ? (
          <div className="rounded-xl border border-gray-200 p-6">
            <p className="text-gray-500 text-center">No transactions yet</p>
          </div>
        ) : (
          <div className="space-y-4">
            {transactions.slice(0, showMoreTransactions ? undefined : 5).map((transaction) => (
              <div key={transaction.id} className="rounded-xl border border-gray-200 p-6">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h4 className="font-semibold text-gray-900">{transaction.service_name}</h4>
                    <p className="text-sm text-gray-600">{transaction.instructor_name}</p>
                  </div>
                  <p className="text-sm text-gray-500">{formatDate(transaction.booking_date)}</p>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Lesson ({transaction.duration_minutes} min)</span>
                    <span className="font-medium">{formatCurrency(transaction.total_price)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Service fee</span>
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
