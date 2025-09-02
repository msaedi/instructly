'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  CreditCard,
  CheckCircle,
  AlertCircle,
  ArrowRight,
  Loader2,
  ExternalLink,
  RefreshCw,
  Shield,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { paymentService } from '@/services/api/payments';
import type { OnboardingStatusResponse } from '@/services/api/payments';

interface StripeOnboardingProps {
  instructorId: string;
}

const StripeOnboarding: React.FC<StripeOnboardingProps> = ({ instructorId }) => {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [pollAttempts, setPollAttempts] = useState(0);

  // Check if we're returning from Stripe
  const isReturningFromStripe = searchParams.get('stripe_onboarding_return') === 'true';

  // Fetch onboarding status
  const checkStatus = useCallback(async () => {
    try {
      const status = await paymentService.getOnboardingStatus();
      setOnboardingStatus(status);
      logger.info('Onboarding status fetched', status);

      // If completed, stop polling
      if (status.onboarding_completed && isPolling) {
        setIsPolling(false);
        setPollAttempts(0);

        // Clear URL params
        const url = new URL(window.location.href);
        url.searchParams.delete('stripe_onboarding_return');
        window.history.replaceState({}, '', url.toString());
      }

      return status;
    } catch (err) {
      logger.error('Error fetching onboarding status:', err);
      setError('Failed to load onboarding status');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [isPolling]);

  // Initial status check
  useEffect(() => {
    checkStatus();
  }, [instructorId]);

  // Polling logic for when returning from Stripe
  useEffect(() => {
    if (isReturningFromStripe && !onboardingStatus?.onboarding_completed) {
      setIsPolling(true);
      logger.info('Starting polling after Stripe redirect');
    }
  }, [isReturningFromStripe, onboardingStatus?.onboarding_completed]);

  // Poll for status updates
  useEffect(() => {
    if (!isPolling || pollAttempts >= 15) {
      if (pollAttempts >= 15) {
        logger.warn('Polling timeout reached');
        setIsPolling(false);
        setPollAttempts(0);
      }
      return;
    }

    const pollInterval = setInterval(() => {
      setPollAttempts((prev) => prev + 1);
      checkStatus();
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(pollInterval);
  }, [isPolling, pollAttempts, checkStatus]);

  // Start or continue onboarding
  const startOnboarding = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await paymentService.startOnboarding();
      logger.info('Onboarding initiated', response);

      if (response.already_onboarded) {
        // Already completed, just refresh status
        await checkStatus();
      } else if (response.onboarding_url) {
        // Redirect to Stripe
        window.location.href = response.onboarding_url;
      }
    } catch (err) {
      logger.error('Error starting onboarding:', err);
      setError('Failed to start onboarding. Please try again.');
      setLoading(false);
    }
  };

  // Open Stripe Express dashboard
  const openDashboard = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await paymentService.getDashboardLink();
      logger.info('Dashboard link fetched', response);

      if (response.dashboard_url) {
        window.open(response.dashboard_url, '_blank');
      }
    } catch (err) {
      logger.error('Error opening dashboard:', err);
      setError('Failed to open dashboard. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Render loading state
  if (loading && !isPolling) {
    return (
      <Card className="p-8">
        <div className="flex justify-center items-center">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </Card>
    );
  }

  // Render polling state
  if (isPolling) {
    return (
      <Card className="p-8">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 mx-auto mb-4 text-blue-500 animate-spin" />
          <h3 className="text-lg font-semibold mb-2">Verifying Your Account</h3>
          <p className="text-gray-600 mb-4">
            We&apos;re checking your Stripe account status. This should only take a moment...
          </p>
          <p className="text-sm text-gray-500">
            Checking status... (Attempt {pollAttempts}/15)
          </p>
        </div>
      </Card>
    );
  }

  // Render error state
  if (error && !onboardingStatus) {
    return (
      <Card className="p-8">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 text-red-500" />
          <h3 className="text-lg font-semibold mb-2">Connection Error</h3>
          <p className="text-gray-600 mb-4">{error}</p>
          <Button onClick={() => window.location.reload()}>
            Try Again
          </Button>
        </div>
      </Card>
    );
  }

  // Not connected state
  if (!onboardingStatus?.has_account) {
    return (
      <Card className="p-8">
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0">
            <div className="h-12 w-12 rounded-full bg-blue-100 flex items-center justify-center">
              <CreditCard className="h-6 w-6 text-blue-600" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-semibold mb-2">Connect Your Stripe Account</h3>
            <p className="text-gray-600 mb-4">
              To receive payments from students, you need to connect a Stripe account.
              This secure process takes just a few minutes.
            </p>

            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <h4 className="font-medium mb-2">What you&apos;ll need:</h4>
              <ul className="space-y-1 text-sm text-gray-600">
                <li>• Business or personal bank account details</li>
                <li>• Tax identification number (SSN or EIN)</li>
                <li>• Business address (or home address)</li>
                <li>• Phone number for verification</li>
              </ul>
            </div>

            <div className="flex items-center space-x-2 text-sm text-gray-500 mb-6">
              <Shield className="h-4 w-4" />
              <span>Secure connection powered by Stripe</span>
            </div>

            <Button
              onClick={startOnboarding}
              disabled={loading}
              size="lg"
              className="w-full sm:w-auto"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Connecting...
                </>
              ) : (
                <>
                  Connect Stripe Account
                  <ArrowRight className="h-4 w-4 ml-2" />
                </>
              )}
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  // Onboarding incomplete state
  if (onboardingStatus.has_account && !onboardingStatus.onboarding_completed) {
    return (
      <Card className="p-8">
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0">
            <div className="h-12 w-12 rounded-full bg-yellow-100 flex items-center justify-center">
              <AlertCircle className="h-6 w-6 text-yellow-600" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-semibold mb-2">Complete Your Setup</h3>
            <p className="text-gray-600 mb-4">
              Your Stripe account setup is almost complete. Please finish the remaining steps to start receiving payments.
            </p>

            {onboardingStatus.requirements && onboardingStatus.requirements.length > 0 && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
                <h4 className="font-medium mb-2 text-yellow-900">Remaining Requirements:</h4>
                <ul className="space-y-1 text-sm text-yellow-800">
                  {onboardingStatus.requirements.map((req, index) => (
                    <li key={index}>• {req}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
              <div className="flex items-center space-x-2">
                <span className="text-gray-500">Charges enabled:</span>
                {onboardingStatus.charges_enabled ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-gray-400" />
                )}
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-gray-500">Payouts enabled:</span>
                {onboardingStatus.payouts_enabled ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-gray-400" />
                )}
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-gray-500">Details submitted:</span>
                {onboardingStatus.details_submitted ? (
                  <CheckCircle className="h-4 w-4 text-green-500" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-gray-400" />
                )}
              </div>
            </div>

            <Button
              onClick={startOnboarding}
              disabled={loading}
              size="lg"
              className="w-full sm:w-auto"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Loading...
                </>
              ) : (
                <>
                  Continue Setup
                  <ArrowRight className="h-4 w-4 ml-2" />
                </>
              )}
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  // Onboarding complete state
  if (onboardingStatus.onboarding_completed) {
    return (
      <Card className="p-8">
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0">
            <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
              <CheckCircle className="h-6 w-6 text-green-600" />
            </div>
          </div>
          <div className="flex-1">
            <h3 className="text-xl font-semibold mb-2">Stripe Account Connected</h3>
            <p className="text-gray-600 mb-6">
              Your Stripe account is fully set up and ready to receive payments from students.
            </p>

            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <span className="text-green-900">Charges enabled</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <span className="text-green-900">Payouts enabled</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <span className="text-green-900">Details verified</span>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-600" />
                  <span className="text-green-900">Ready for payments</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                onClick={openDashboard}
                disabled={loading}
                size="lg"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Opening...
                  </>
                ) : (
                  <>
                    View Payouts Dashboard
                    <ExternalLink className="h-4 w-4 ml-2" />
                  </>
                )}
              </Button>

              <Button
                variant="outline"
                onClick={() => checkStatus()}
                disabled={loading}
                size="lg"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh Status
              </Button>
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}
          </div>
        </div>
      </Card>
    );
  }

  return null;
};

export default StripeOnboarding;
