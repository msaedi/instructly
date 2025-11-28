'use client';

import React, { useState, useMemo } from 'react';
import {
  DollarSign,
  TrendingUp,
  Calendar,
  ExternalLink,
  Download,
  CreditCard,
  Info,
  Loader2,
  AlertCircle,
  Clock,
  FileText,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { paymentService } from '@/services/api/payments';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';

interface PayoutsDashboardProps {
  instructorId: string;
}

const PayoutsDashboard: React.FC<PayoutsDashboardProps> = ({ instructorId: _instructorId }) => {
  const [, setDashboardUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openingDashboard, setOpeningDashboard] = useState(false);

  // Use React Query hook for earnings data (prevents duplicate API calls)
  const { data: earnings, isLoading: loading, error: queryError } = useInstructorEarnings();

  // Show query error if present
  const displayError = error || (queryError ? 'Failed to load earnings data' : null);

  const { config: pricingConfig } = usePricingConfig();
  const platformFeePct = useMemo(() => {
    const tiers = pricingConfig?.instructor_tiers ?? [];
    if (!tiers.length) return null;
    const sorted = [...tiers].sort((a, b) => (a.min ?? 0) - (b.min ?? 0));
    const pct = sorted[0]?.pct;
    return typeof pct === 'number' ? pct : null;
  }, [pricingConfig]);
  const platformFeeLabel = useMemo(() => {
    if (platformFeePct == null) return null;
    const percent = platformFeePct * 100;
    return percent % 1 === 0 ? `${percent.toFixed(0)}%` : `${percent.toFixed(1)}%`;
  }, [platformFeePct]);

  // Open Stripe Express dashboard
  const openStripeDashboard = async () => {
    try {
      setOpeningDashboard(true);
      setError(null);

      const response = await paymentService.getDashboardLink();
      logger.info('Dashboard link fetched', response);

      if (response.dashboard_url) {
        setDashboardUrl(response.dashboard_url);
        window.open(response.dashboard_url, '_blank');
      }
    } catch (err) {
      logger.error('Error opening dashboard:', err);
      setError('Failed to open Stripe dashboard. Please try again.');
    } finally {
      setOpeningDashboard(false);
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
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Card className="p-8">
          <div className="flex justify-center items-center">
            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Earnings Overview */}
      <div>
        <h2 className="text-2xl font-semibold mb-4">Payouts & Earnings</h2>

        {earnings && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {/* Total Earnings Card */}
            <Card className="p-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-gray-500 mb-1">Total Earnings</p>
                  <p className="text-3xl font-bold text-gray-900">
                    {formatCurrency(earnings.total_earned)}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    This month ({formatDate(earnings.period_start || '2025-08-01')} - {formatDate(earnings.period_end || '2025-08-31')})
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center">
                  <DollarSign className="h-5 w-5 text-green-600" />
                </div>
              </div>
            </Card>

            {/* Bookings Card */}
            <Card className="p-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-gray-500 mb-1">Total Bookings</p>
                  <p className="text-3xl font-bold text-gray-900">
                    {earnings.booking_count}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Avg. {formatCurrency(earnings.average_earning)} per session
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
                  <Calendar className="h-5 w-5 text-blue-600" />
                </div>
              </div>
            </Card>

            {/* Platform Fees Card */}
            <Card className="p-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-gray-500 mb-1">Platform Fees</p>
                  <p className="text-3xl font-bold text-gray-900">
                    {formatCurrency(earnings.total_fees)}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    {platformFeeLabel ? `${platformFeeLabel} service fee` : 'Platform fees withheld'}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center">
                  <TrendingUp className="h-5 w-5 text-gray-600" />
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Quick Actions</h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Button
            onClick={openStripeDashboard}
            disabled={openingDashboard}
            size="lg"
            className="w-full"
          >
            {openingDashboard ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Opening...
              </>
            ) : (
              <>
                <ExternalLink className="h-4 w-4 mr-2" />
                View Stripe Dashboard
              </>
            )}
          </Button>

          <Button
            variant="outline"
            onClick={openStripeDashboard}
            disabled={openingDashboard}
            size="lg"
            className="w-full"
          >
            <CreditCard className="h-4 w-4 mr-2" />
            Update Banking Info
          </Button>

          <Button
            variant="outline"
            onClick={openStripeDashboard}
            disabled={openingDashboard}
            size="lg"
            className="w-full"
          >
            <Download className="h-4 w-4 mr-2" />
            Tax Documents
          </Button>
        </div>

        {displayError && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-2">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <p className="text-sm text-red-700">{displayError}</p>
          </div>
        )}

        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start space-x-2">
            <Info className="h-5 w-5 text-blue-600 mt-0.5" />
            <div className="text-sm text-blue-900">
              <p className="font-medium mb-1">Detailed Analytics Available in Stripe</p>
              <p className="text-blue-700">
                Access comprehensive reports, transaction history, and tax documents directly in your Stripe Express dashboard.
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* Payout Information */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Payout Information</h3>

        <div className="space-y-4">
          {/* Payout Schedule */}
          <div className="flex items-start space-x-3">
            <Clock className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium text-gray-900">Payout Schedule</p>
              <p className="text-sm text-gray-600">
                Standard 2-day rolling basis. Funds from bookings are automatically transferred to your bank account.
              </p>
            </div>
          </div>

          {/* Platform Fee */}
          <div className="flex items-start space-x-3">
            <DollarSign className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium text-gray-900">Platform Fee Structure</p>
        <p className="text-sm text-gray-600">
          iNSTAiNSTRU charges a {platformFeeLabel ?? 'standard'} service fee on each booking. This covers payment
          processing, platform maintenance, and customer support.
        </p>
            </div>
          </div>

          {/* Tax Documents */}
          <div className="flex items-start space-x-3">
            <FileText className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium text-gray-900">Tax Documents</p>
              <p className="text-sm text-gray-600">
                1099 forms are automatically generated for qualifying instructors. Access all tax documents through your Stripe dashboard.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">
            <span className="font-medium">Need help with payments?</span> Contact our support team at{' '}
            <a href="mailto:payments@instainstru.com" className="text-blue-600 hover:underline">
              payments@instainstru.com
            </a>{' '}
            or visit our{' '}
            <a href="/help/payments" className="text-blue-600 hover:underline">
              payment help center
            </a>.
          </p>
        </div>
      </Card>

      {/* Earnings Breakdown (Optional - for future enhancement) */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Earnings Breakdown</h3>

        <div className="bg-gray-50 rounded-lg p-8 text-center">
          <TrendingUp className="h-12 w-12 mx-auto mb-3 text-gray-400" />
          <p className="text-gray-600 mb-2">Detailed earnings analytics</p>
          <p className="text-sm text-gray-500 mb-4">
            View comprehensive breakdowns, trends, and insights in your Stripe dashboard
          </p>
          <Button
            variant="outline"
            onClick={openStripeDashboard}
            disabled={openingDashboard}
          >
            Open Analytics
            <ExternalLink className="h-4 w-4 ml-2" />
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default PayoutsDashboard;
