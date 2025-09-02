'use client';

import React, { useEffect, useState } from 'react';
import { Loader2, Shield, CreditCard } from 'lucide-react';
import { BookingType } from '../types';

interface PaymentProcessingProps {
  amount: number;
  bookingType: BookingType;
  onTimeout?: () => void;
}

export default function PaymentProcessing({
  amount,
  bookingType,
  onTimeout,
}: PaymentProcessingProps) {
  const [processingStep, setProcessingStep] = useState(0);
  const isLastMinute = bookingType === BookingType.LAST_MINUTE;

  const steps = isLastMinute
    ? [
        'Validating payment method',
        'Processing payment',
        'Confirming with instructor',
        'Creating your booking',
      ]
    : [
        'Validating payment method',
        'Authorizing card',
        'Confirming with instructor',
        'Reserving your lesson',
      ];

  useEffect(() => {
    const interval = setInterval(() => {
      setProcessingStep((prev) => {
        if (prev < steps.length - 1) {
          return prev + 1;
        }
        return prev;
      });
    }, 1500);

    // Timeout after 30 seconds
    const timeout = setTimeout(() => {
      if (onTimeout) {
        onTimeout();
      }
    }, 30000);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [steps.length, onTimeout]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        {/* Spinner */}
        <div className="mb-8 relative">
          <div className="w-24 h-24 mx-auto relative">
            <Loader2 className="w-24 h-24 text-[#FFD700] animate-spin" />
            <div className="absolute inset-0 flex items-center justify-center">
              <CreditCard className="w-10 h-10 text-gray-600 dark:text-gray-400" />
            </div>
          </div>
        </div>

        {/* Main Message */}
        <h2 className="text-2xl font-bold mb-2">
          {isLastMinute ? 'Processing Payment' : 'Authorizing Payment'}
        </h2>
        <p className="text-gray-600 dark:text-gray-400 mb-8">
          {isLastMinute
            ? `Charging $${amount.toFixed(2)} to your card`
            : `Authorizing $${amount.toFixed(2)} for your lesson`}
        </p>

        {/* Progress Steps */}
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-6 mb-8">
          <div className="space-y-3">
            {steps.map((step, index) => (
              <div
                key={index}
                className={`flex items-center text-sm transition-all duration-500 ${
                  index <= processingStep
                    ? 'text-gray-900 dark:text-gray-100'
                    : 'text-gray-400 dark:text-gray-500'
                }`}
              >
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center mr-3 transition-all duration-500 ${
                    index < processingStep
                      ? 'bg-green-500 text-white'
                      : index === processingStep
                        ? 'bg-[#FFD700] text-black'
                        : 'bg-gray-300 dark:bg-gray-600'
                  }`}
                >
                  {index < processingStep ? (
                    '✓'
                  ) : index === processingStep ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    ''
                  )}
                </div>
                <span className={index === processingStep ? 'font-medium' : ''}>{step}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Security Notice */}
        <div className="flex items-center justify-center text-sm text-gray-500 dark:text-gray-400">
          <Shield className="w-4 h-4 mr-2" />
          <span>Secure payment processed by Stripe</span>
        </div>

        {/* Don't close notice */}
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-4">
          Please don&apos;t close this window
        </p>
      </div>
    </div>
  );
}
