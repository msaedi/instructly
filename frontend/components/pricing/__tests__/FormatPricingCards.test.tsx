import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormatPricingCards } from '../FormatPricingCards';
import type { FormatPriceState, ServiceFormat } from '@/lib/pricing/formatPricing';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';

const mockFloors: PriceFloorConfig = {
  private_in_person: 8000,
  private_remote: 6000,
};

const defaultProps = {
  formatPrices: {} as FormatPriceState,
  onChange: jest.fn(),
  priceFloors: mockFloors,
  durationOptions: [60],
  takeHomePct: 0.8,
  platformFeeLabel: '20%',
};

type RenderOverrides = Partial<typeof defaultProps> & {
  formatErrors?: Partial<Record<ServiceFormat, string>>;
  emptyRateErrors?: Partial<Record<ServiceFormat, boolean>>;
  studentLocationDisabled?: boolean;
  studentLocationDisabledReason?: string;
};

function renderCards(overrides: RenderOverrides = {}) {
  const props = { ...defaultProps, onChange: jest.fn(), ...overrides };
  const result = render(<FormatPricingCards {...props} />);
  return { ...result, onChange: props.onChange };
}

describe('FormatPricingCards', () => {
  it('renders all three format cards with correct labels', () => {
    renderCards();
    expect(screen.getByText("At Student's Location")).toBeInTheDocument();
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.getByText("At Instructor's Location")).toBeInTheDocument();
  });

  it('renders descriptions for each card', () => {
    renderCards();
    expect(
      screen.getByText(/You go to the student/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Live video lesson/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Students come to you/)
    ).toBeInTheDocument();
  });

  it('all cards start greyed out when formatPrices is empty', () => {
    const { container } = renderCards();
    const cards = container.querySelectorAll('[data-testid^="format-card-"]');
    expect(cards).toHaveLength(3);
    cards.forEach((card) => {
      expect(card.className).toMatch(/opacity-/);
    });
  });

  it('toggling a card ON calls onChange with that format key set to empty string', async () => {
    const user = userEvent.setup();
    const { onChange } = renderCards();

    const toggles = screen.getAllByRole('switch');
    // First toggle is student_location
    await user.click(toggles[0]!);

    expect(onChange).toHaveBeenCalledWith({ student_location: '' });
  });

  it('toggling a card OFF calls onChange without that format key', async () => {
    const user = userEvent.setup();
    const { onChange } = renderCards({
      formatPrices: { student_location: '100', online: '80' },
    });

    // First toggle is student_location — currently ON, click to turn OFF
    const toggles = screen.getAllByRole('switch');
    await user.click(toggles[0]!);

    // Should have online but NOT student_location
    expect(onChange).toHaveBeenCalledWith({ online: '80' });
  });

  it('rate input updates call onChange with new rate value', async () => {
    const user = userEvent.setup();
    const { onChange } = renderCards({
      formatPrices: { online: '' },
    });

    // The online card's input is the only enabled one
    const enabledInputs = screen.getAllByRole('spinbutton').filter(
      (el) => !(el as HTMLInputElement).disabled
    );
    expect(enabledInputs).toHaveLength(1);
    await user.type(enabledInputs[0]!, '9');

    expect(onChange).toHaveBeenCalledWith({ online: '9' });
  });

  it('rate inputs are disabled when format is off', () => {
    renderCards({ formatPrices: {} });
    const inputs = screen.getAllByRole('spinbutton');
    inputs.forEach((input) => {
      expect(input).toBeDisabled();
    });
  });

  it('rate input is enabled when format is on', () => {
    renderCards({ formatPrices: { online: '80' } });
    const input = screen.getByDisplayValue('80');
    expect(input).not.toBeDisabled();
  });

  it('shows take-home display when rate is greater than 0', () => {
    renderCards({
      formatPrices: { online: '100' },
      takeHomePct: 0.8,
      platformFeeLabel: '20%',
    });
    // $100 * 0.8 = $80.00
    expect(screen.getByText('$80.00')).toBeInTheDocument();
    expect(screen.getByText(/20% platform fee/)).toBeInTheDocument();
  });

  it('does not show take-home when rate is empty', () => {
    renderCards({
      formatPrices: { online: '' },
    });
    expect(screen.queryByText(/platform fee/)).not.toBeInTheDocument();
  });

  it('renders format errors inline under the correct card', () => {
    renderCards({
      formatPrices: { student_location: '50' },
      formatErrors: { student_location: 'Rate is below the minimum' },
    });
    expect(screen.getByText('Rate is below the minimum')).toBeInTheDocument();
  });

  it('renders empty-rate errors inline with alert semantics', () => {
    renderCards({
      formatPrices: { student_location: '' },
      emptyRateErrors: { student_location: true },
    });

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Enter a rate to activate this lesson type.');
    const enabledInput = screen.getAllByRole('spinbutton').find(
      (element) => !(element as HTMLInputElement).disabled
    );
    expect(enabledInput).toHaveAttribute('aria-invalid', 'true');
  });

  it('shows the max hourly rate validation message at $1,001', () => {
    renderCards({
      formatPrices: { online: '1001' },
    });

    expect(screen.getByText('Maximum hourly rate is $1,000')).toBeInTheDocument();
  });

  it('disabled card (studentLocationDisabled) shows reason and toggle is disabled', () => {
    renderCards({
      studentLocationDisabled: true,
      studentLocationDisabledReason: 'Add service areas first',
    });

    const toggles = screen.getAllByRole('switch');
    // First toggle (student_location) should be disabled
    expect(toggles[0]).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Add service areas first')).toBeInTheDocument();
  });

  it('instructor_location card is never disabled (no prerequisite gating)', () => {
    renderCards();

    const toggles = screen.getAllByRole('switch');
    // Third toggle (instructor_location) should NOT be disabled
    expect(toggles[2]).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('shows floor-based placeholder per format (80/60/80)', () => {
    renderCards();
    const inputs = screen.getAllByRole('spinbutton');
    // Order: student_location (80), online (60), instructor_location (80)
    expect(inputs[0]).toHaveAttribute('placeholder', '80');
    expect(inputs[1]).toHaveAttribute('placeholder', '60');
    expect(inputs[2]).toHaveAttribute('placeholder', '80');
  });

  it('instructor_location card is freely toggleable without prerequisites', async () => {
    const user = userEvent.setup();
    const { onChange } = renderCards();

    const toggles = screen.getAllByRole('switch');
    // Third toggle is instructor_location
    await user.click(toggles[2]!);
    expect(onChange).toHaveBeenCalledWith({ instructor_location: '' });
  });

  it('does not render duplicate /hr text', () => {
    renderCards({ formatPrices: { online: '80' } });
    // Should have exactly 3 "/hr" suffixes (one per card), not 6
    const hrTexts = screen.getAllByText('/hr');
    expect(hrTexts).toHaveLength(3);
  });

  it('enabled card has full opacity', () => {
    const { container } = renderCards({
      formatPrices: { online: '80' },
    });
    const onlineCard = container.querySelector('[data-testid="format-card-online"]');
    expect(onlineCard?.className).not.toMatch(/opacity-40/);
  });
});
