import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { useMemo, useState } from 'react';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { evaluatePriceFloorViolations, formatCents } from '@/lib/pricing/priceFloors';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({
    floors: { private_in_person: 8000, private_remote: 6500 },
    isLoading: false,
    error: null,
  }),
  usePricingConfig: () => ({
    config: {
      student_fee_pct: 0.12,
      instructor_tiers: [{ min: 1, max: 4, pct: 0.15 }],
      price_floor_cents: { private_in_person: 8000, private_remote: 6500 },
    },
    isLoading: false,
    error: null,
  }),
}));

function PricingSectionHarness() {
  const { floors } = usePricingFloors();
  const [hourlyRate, setHourlyRate] = useState('80');

  const violations = useMemo(() => {
    if (!floors) return [];
    return evaluatePriceFloorViolations({
      hourlyRate: Number(hourlyRate),
      durationOptions: [60],
      locationTypes: ['in_person'],
      floors,
    });
  }, [floors, hourlyRate]);

  const hasViolation = violations.length > 0;

  return (
    <div>
      <label htmlFor="hourly-rate">Hourly Rate</label>
      <input
        id="hourly-rate"
        type="number"
        value={hourlyRate}
        onChange={(event) => setHourlyRate(event.target.value)}
      />

      {violations.map((violation) => (
        <p key={`${violation.modalityLabel}-${violation.duration}`}>
          Minimum for {violation.modalityLabel} {violation.duration}-minute private session is $
          {formatCents(violation.floorCents)} (current ${formatCents(violation.baseCents)}).
        </p>
      ))}

      <button type="button" disabled={hasViolation}>
        Save & Continue
      </button>
    </div>
  );
}

describe('Onboarding pricing guidance (simplified harness)', () => {
  it('disables saving and shows guidance when instructor pricing is below floor', async () => {
    render(<PricingSectionHarness />);

    const saveButton = screen.getByRole('button', { name: /Save & Continue/i });
    expect(saveButton).not.toBeDisabled();

    const input = screen.getByLabelText(/Hourly Rate/i);
    fireEvent.change(input, { target: { value: '50' } });

    await waitFor(() => {
      expect(
        screen.getByText(/Minimum for in-person 60-minute private session/i)
      ).toBeInTheDocument();
    });

    expect(saveButton).toBeDisabled();

    fireEvent.change(input, { target: { value: '90' } });

    await waitFor(() => {
      expect(
        screen.queryByText(/Minimum for in-person 60-minute private session/i)
      ).not.toBeInTheDocument();
    });

    expect(saveButton).not.toBeDisabled();
  });
});
