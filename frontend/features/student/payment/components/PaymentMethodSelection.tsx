'use client';

import React, { useState } from 'react';
import { CreditCard, Plus, Check } from 'lucide-react';
import { PaymentCard, CreditBalance, BookingPayment, PaymentMethod } from '../types';

interface PaymentMethodSelectionProps {
  booking: BookingPayment;
  cards: PaymentCard[];
  credits: CreditBalance;
  onSelectPayment: (method: PaymentMethod, cardId?: string, creditsToUse?: number) => void;
  onAddCard: () => void;
  onBack?: () => void;
}

export default function PaymentMethodSelection({
  booking,
  cards,
  credits,
  onSelectPayment,
  onAddCard,
  onBack,
}: PaymentMethodSelectionProps) {
  const [selectedCardId, setSelectedCardId] = useState<string>(cards[0]?.id || '');
  const [useCredits, setUseCredits] = useState(false);
  const [creditsToApply, setCreditsToApply] = useState(0);

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

  return (
    <div className="p-6">
      {/* Credits Section */}
      {credits.totalAmount > 0 && (
        <div className="mb-6 p-4 bg-[#FFFEF5] dark:bg-gray-800/50 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-semibold">Available Credits</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Balance: ${credits.totalAmount.toFixed(2)}
              </p>
            </div>
            <button
              onClick={handleCreditToggle}
              className={`p-2 rounded-lg border transition-colors ${
                useCredits
                  ? 'bg-[#FFD700] border-[#FFD700] text-black'
                  : 'border-gray-300 dark:border-gray-600'
              }`}
            >
              {useCredits ? <Check size={20} /> : <Plus size={20} />}
            </button>
          </div>

          {useCredits && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-sm">
                <span>Credits to apply:</span>
                <span className="font-medium">${creditsToApply.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min="0"
                max={maxCreditsApplicable}
                value={creditsToApply}
                onChange={(e) => setCreditsToApply(Number(e.target.value))}
                className="w-full mt-2"
              />
            </div>
          )}

          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            Credits expire 6 months after issue date
          </p>
        </div>
      )}

      {/* Payment Cards */}
      <div className="mb-6">
        <h3 className="font-semibold mb-3">
          {remainingAfterCredits > 0 ? 'Payment Card' : 'Backup Payment Method'}
        </h3>

        <div className="space-y-3">
          {cards.map((card) => (
            <label
              key={card.id}
              className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors ${
                selectedCardId === card.id
                  ? 'border-[#FFD700] bg-[#FFFEF5] dark:bg-gray-800/50'
                  : 'border-gray-300 dark:border-gray-600'
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
              <CreditCard className="mr-3" size={24} />
              <div className="flex-1">
                <p className="font-medium">
                  {card.brand} •••• {card.last4}
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Expires {card.expiryMonth}/{card.expiryYear}
                </p>
              </div>
              {selectedCardId === card.id && <Check className="text-[#FFD700]" size={20} />}
            </label>
          ))}

          <button
            onClick={onAddCard}
            className="w-full p-4 border border-dashed border-gray-300 dark:border-gray-600 rounded-lg hover:border-[#FFD700] transition-colors flex items-center justify-center"
          >
            <Plus size={20} className="mr-2" />
            Add New Card
          </button>
        </div>
      </div>

      {/* Payment Summary */}
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 mb-6">
        <h3 className="font-semibold mb-3">Payment Summary</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span>Lesson Total</span>
            <span>${booking.totalAmount.toFixed(2)}</span>
          </div>
          {creditsToApply > 0 && (
            <>
              <div className="flex justify-between text-green-600 dark:text-green-400">
                <span>Credits Applied</span>
                <span>-${creditsToApply.toFixed(2)}</span>
              </div>
              <div className="border-t pt-2 mt-2">
                <div className="flex justify-between font-semibold">
                  <span>Amount Due</span>
                  <span>${remainingAfterCredits.toFixed(2)}</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Transaction Limit Notice */}
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-6 text-center">
        Maximum transaction limit: $1,000
      </p>

      {/* Action Buttons */}
      <div className="flex gap-3">
        {onBack && (
          <button
            onClick={onBack}
            className="flex-1 py-3 border border-gray-300 dark:border-gray-600 rounded-full font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Back
          </button>
        )}
        <button
          onClick={handleContinue}
          className={`${onBack ? 'flex-1' : 'w-full'} py-3 bg-[#FFD700] hover:bg-[#FFC700] text-black rounded-full font-medium transition-colors`}
        >
          Continue to Confirmation
        </button>
      </div>
    </div>
  );
}
