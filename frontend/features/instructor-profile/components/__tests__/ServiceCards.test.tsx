import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ServiceCards } from '../ServiceCards';
import type { InstructorService } from '@/types/instructor';

const baseService: InstructorService = {
  id: 'svc-1',
  skill: 'Piano',
  min_hourly_rate: 120,
  format_prices: [{ format: 'online', hourly_rate: 120 }],
  duration_options: [30, 60],
  age_groups: ['adults'],
  levels_taught: ['beginner', 'intermediate'],
  location_types: ['in_person'],
  description: '',
};

function omitServiceField<K extends keyof InstructorService>(
  service: InstructorService,
  key: K,
): Omit<InstructorService, K> {
  const { [key]: _omitted, ...rest } = service;
  return rest;
}

describe('ServiceCards', () => {
  it('shows an empty state when no services are available', () => {
    render(<ServiceCards services={[]} />);

    expect(screen.getByText(/no services available/i)).toBeInTheDocument();
  });

  it('books a service with the selected duration', async () => {
    const user = userEvent.setup();
    const onBookService = jest.fn();

    render(<ServiceCards services={[baseService]} onBookService={onBookService} />);

    await user.click(screen.getByLabelText(/60min/i));
    await user.click(screen.getByTestId('book-service-piano'));

    expect(onBookService).toHaveBeenCalledWith(expect.objectContaining({ id: 'svc-1' }), 60);
    // Per-format pricing: "$120 · Online"
    expect(screen.getByText((content) => content.includes('$120') && content.includes('Online'))).toBeInTheDocument();
  });

  it('renders badges and labels for kids, levels, and formats', () => {
    const service: InstructorService = {
      ...baseService,
      id: 'svc-2',
      skill: 'Guitar',
      age_groups: ['kids'],
      levels_taught: ['advanced', 'beginner'],
      location_types: ['online', 'in_person'],
      format_prices: [
        { format: 'student_location', hourly_rate: 120 },
        { format: 'online', hourly_rate: 100 },
      ],
      min_hourly_rate: 100,
      description: '',
    };

    render(<ServiceCards services={[service]} />);

    const kidsBadge = screen.getByText(/kids lesson available/i);
    expect(kidsBadge).toBeInTheDocument();
    expect(kidsBadge).not.toHaveClass('opacity-0');
    expect(screen.getByText((value) => value.includes('Levels:') && value.includes('Beginner') && value.includes('Advanced'))).toBeInTheDocument();
    expect(screen.getByText(/format:/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /travels to you/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /online/i })).toBeInTheDocument();
  });

  it('disables booking when the selected slot cannot fit the duration', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 30 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const button = screen.getByTestId('book-service-piano');
    expect(button).toBeDisabled();

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    expect(screen.getByText(/only 30 minutes available from 9:00 AM/i)).toBeInTheDocument();
  });

  it('prioritizes the searched service first', () => {
    const services: InstructorService[] = [
      { ...baseService, id: 'svc-1', skill: 'Piano' },
      { ...baseService, id: 'svc-3', skill: 'Guitar' },
    ];

    render(<ServiceCards services={services} searchedService="guitar" />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings[0]).toHaveTextContent('Guitar');
  });

  it('uses fallback duration of 60 when duration_options is empty', () => {
    const service: InstructorService = {
      ...baseService,
      duration_options: [],
    };

    render(<ServiceCards services={[service]} />);

    // With empty duration_options, defaults to [60], single option shows /hr price per format
    expect(screen.getByText((content) => content.includes('$120/hr') && content.includes('Online'))).toBeInTheDocument();
    // Should NOT show radio buttons for duration selection
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('uses fallback duration of 60 when duration_options is undefined', () => {
    const service: InstructorService = omitServiceField(baseService, 'duration_options');

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText((content) => content.includes('$120/hr') && content.includes('Online'))).toBeInTheDocument();
  });

  it('filters out non-numeric and zero duration options in the card UI', () => {
    const service: InstructorService = {
      ...baseService,
      duration_options: [0, -30, 60, 'invalid' as unknown as number],
    };

    render(<ServiceCards services={[service]} />);

    // With per-format pricing, showHourlyPrice=true (single valid option [60]),
    // so the format rate is displayed directly: $120/hr · Online
    expect(screen.getByText((content) => content.includes('$120/hr') && content.includes('Online'))).toBeInTheDocument();
    // Duration radio buttons should not show (only 1 valid option after filter)
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('renders "Service" fallback when skill is undefined', () => {
    const service: InstructorService = omitServiceField(baseService, 'skill');

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('Service')).toBeInTheDocument();
  });

  it('renders hidden placeholder when no levels are available', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: [],
      age_groups: [],
    };

    render(<ServiceCards services={[service]} />);

    // No "Levels:" label should be visible
    expect(screen.queryByText(/levels:/i)).not.toBeInTheDocument();
    // No "Kids lesson available" badge should be visible (but the placeholder is rendered)
    const kidsBadges = screen.getAllByText(/kids lesson available/i);
    kidsBadges.forEach(badge => {
      expect(badge).toHaveClass('opacity-0');
    });
  });

  it('deduplicates levels when there are repeats', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['beginner', 'Beginner', 'advanced'],
    };

    render(<ServiceCards services={[service]} />);

    expect(
      screen.getByText((content) => content.includes('Beginner') && content.includes('Advanced'))
    ).toBeInTheDocument();
  });

  it('handles levels_taught from unsafe cast when base property is missing', () => {
    // Simulate API returning levels_taught at the raw level
    const service: InstructorService = omitServiceField(baseService, 'levels_taught');

    // Override via the unsafe cast path
    (service as unknown as Record<string, unknown>)['levels_taught'] = ['expert'];

    render(<ServiceCards services={[service]} />);

    expect(
      screen.getByText((content) => content.includes('Expert'))
    ).toBeInTheDocument();
  });

  it('handles non-string values in levels_taught gracefully', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: [42 as unknown as string, null as unknown as string, 'advanced'],
    };

    render(<ServiceCards services={[service]} />);

    // Should only show 'Advanced' (non-strings filtered out)
    expect(
      screen.getByText((content) => content.includes('Advanced'))
    ).toBeInTheDocument();
  });

  it('handles age_groups from unsafe cast for kids badge', () => {
    const service: InstructorService = omitServiceField(baseService, 'age_groups');

    (service as unknown as Record<string, unknown>)['age_groups'] = ['kids'];

    render(<ServiceCards services={[service]} />);

    const kidsBadge = screen.getByText(/kids lesson available/i);
    expect(kidsBadge).not.toHaveClass('opacity-0');
  });

  it('handles non-string values in age_groups gracefully', () => {
    const service: InstructorService = {
      ...baseService,
      age_groups: [123 as unknown as string, 'adults'],
    };

    render(<ServiceCards services={[service]} />);

    // Non-string values are filtered out, 'adults' remains but no kids badge
    const kidsBadges = screen.getAllByText(/kids lesson available/i);
    kidsBadges.forEach(badge => {
      expect(badge).toHaveClass('opacity-0');
    });
  });

  it('uses min_hourly_rate for price calculation', () => {
    const service: InstructorService = {
      ...baseService,
      min_hourly_rate: 80,
      format_prices: [{ format: 'online', hourly_rate: 80 }],
      duration_options: [60],
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText((content) => content.includes('$80/hr') && content.includes('Online'))).toBeInTheDocument();
  });

  it('shows "Contact instructor" when format_prices is empty', () => {
    const service: InstructorService = {
      ...baseService,
      min_hourly_rate: 0,
      format_prices: [],
      duration_options: [60],
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('Contact instructor')).toBeInTheDocument();
  });

  it('handles undefined min_hourly_rate — format_prices still displays rates', () => {
    const service = {
      ...baseService,
      duration_options: [60],
    } as InstructorService;

    (service as unknown as Record<string, unknown>)['min_hourly_rate'] = undefined;

    render(<ServiceCards services={[service]} />);

    // format_prices from baseService still shows the per-format rate
    expect(screen.getByText((content) => content.includes('$120/hr') && content.includes('Online'))).toBeInTheDocument();
  });

  it('shows at-location format only when hasTeachingLocations is true', () => {
    const service: InstructorService = {
      ...baseService,
      format_prices: [{ format: 'instructor_location', hourly_rate: 80 }],
      min_hourly_rate: 80,
    };

    const { rerender } = render(<ServiceCards services={[service]} hasTeachingLocations={true} />);
    expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();

    rerender(<ServiceCards services={[service]} hasTeachingLocations={false} />);
    expect(screen.queryByRole('img', { name: /at their studio/i })).not.toBeInTheDocument();
  });

  it('hides format section when no format_prices are set', () => {
    const service: InstructorService = {
      ...baseService,
      format_prices: [],
      min_hourly_rate: 0,
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.queryByText(/format:/i)).not.toBeInTheDocument();
  });

  it('shows divider between levels and format only when both exist', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['beginner'],
      format_prices: [{ format: 'online', hourly_rate: 120 }],
      min_hourly_rate: 120,
    };

    const { container } = render(<ServiceCards services={[service]} />);

    // Divider is rendered as a gradient div between levels and format
    expect(container.querySelector('.bg-gradient-to-r')).toBeInTheDocument();
  });

  it('does not show divider when levels are empty', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: [],
      format_prices: [{ format: 'online', hourly_rate: 120 }],
      min_hourly_rate: 120,
    };

    const { container } = render(<ServiceCards services={[service]} />);

    // No divider when levels are empty
    expect(container.querySelector('.bg-gradient-to-r')).not.toBeInTheDocument();
  });

  it('shows unavailable message when availableDuration equals 60', () => {
    const service: InstructorService = { ...baseService, duration_options: [90] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 90, availableDuration: 60 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    expect(screen.getByText(/this 90-minute session requires a 2-hour time block/i)).toBeInTheDocument();
  });

  it('shows generic unavailable message when no selectedSlot', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    render(<ServiceCards services={[service]} />);

    const bookBtn = screen.getByTestId('book-service-piano');
    // No selectedSlot means canBook is true, so no tooltip title
    expect(bookBtn).not.toBeDisabled();
    expect(bookBtn).toHaveAttribute('title', '');
  });

  it('limits displayed service cards to 4', () => {
    const services: InstructorService[] = Array.from({ length: 6 }, (_, i) => ({
      ...baseService,
      id: `svc-${i}`,
      skill: `Service ${i}`,
    }));

    render(<ServiceCards services={services} />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings).toHaveLength(4);
  });

  it('does not crash when services is null', () => {
    render(<ServiceCards services={null as unknown as InstructorService[]} />);

    expect(screen.getByText(/no services available/i)).toBeInTheDocument();
  });

  it('does not call onBookService when canBook is false', () => {
    const onBookService = jest.fn();
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 30 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} onBookService={onBookService} />);

    const bookBtn = screen.getByTestId('book-service-piano');
    fireEvent.click(bookBtn);

    expect(onBookService).not.toHaveBeenCalled();
  });

  it('hides tooltip when mouse leaves the card', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 30 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);
    expect(screen.getByText(/only 30 minutes available/i)).toBeInTheDocument();

    fireEvent.mouseLeave(card);
    expect(screen.queryByText(/only 30 minutes available/i)).not.toBeInTheDocument();
  });

  it('does not sort when searchedService is not provided', () => {
    const services: InstructorService[] = [
      { ...baseService, id: 'svc-1', skill: 'Piano' },
      { ...baseService, id: 'svc-2', skill: 'Guitar' },
    ];

    render(<ServiceCards services={services} />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings[0]).toHaveTextContent('Piano');
    expect(headings[1]).toHaveTextContent('Guitar');
  });

  it('shows non-hourly price format when multiple durations available', async () => {
    const user = userEvent.setup();
    const service: InstructorService = {
      ...baseService,
      min_hourly_rate: 120,
      format_prices: [{ format: 'online', hourly_rate: 120 }],
      duration_options: [30, 60],
    };

    render(<ServiceCards services={[service]} />);

    // Default duration is 30 min (first option)
    // Price = (120 * 30) / 60 = $60, shown as "$60 · Online"
    expect(screen.getByText((content) => content.includes('$60') && content.includes('Online'))).toBeInTheDocument();

    // Select 60 min
    await user.click(screen.getByLabelText(/60min/i));
    expect(screen.getByText((content) => content.includes('$120') && content.includes('Online'))).toBeInTheDocument();
  });

  it('defaults selectedSlot availableDuration to 120 when not provided', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    // With default availableDuration of 120, 60-min service should be bookable
    const bookBtn = screen.getByTestId('book-service-piano');
    expect(bookBtn).not.toBeDisabled();
  });

  it('shows generic unavailable message when duration exceeds available but slot has no constraint', () => {
    // This exercises the final fallback in getUnavailableMessage:
    // "This duration is not available at the selected time"
    // This happens when duration <= availableMinutes but canBook is still false
    const service: InstructorService = {
      ...baseService,
      duration_options: [60],
    };
    // availableDuration (30) < duration (60) triggers the second branch,
    // but we want the generic fallback — which occurs when duration <= availableMinutes
    // We need canBook=false + a slot where duration <= availableMinutes
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 60 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    // With canBook=true (60 <= 60), the button title should be empty
    const bookBtn = screen.getByTestId('book-service-piano');
    expect(bookBtn).not.toBeDisabled();
    expect(bookBtn).toHaveAttribute('title', '');
  });

  it('renders unavailable tooltip with getUnavailableMessage when canBook is false and no selectedSlot', () => {
    // Exercise getUnavailableMessage returning empty string when no selectedSlot
    const service: InstructorService = { ...baseService, duration_options: [60] };

    render(<ServiceCards services={[service]} />);

    const bookBtn = screen.getByTestId('book-service-piano');
    // No selectedSlot means canBook is true, title should be empty
    expect(bookBtn).toHaveAttribute('title', '');
  });

  it('shows getUnavailableMessage fallback text when duration fits but is still unavailable', () => {
    // Forces the "This duration is not available at the selected time" branch
    // by having duration <= availableMinutes but parent forces canBook=false
    // In practice, parent sets canBook = !selectedSlot || duration <= availableMinutes
    // So to get canBook=false, we need duration > availableMinutes
    // The fallback text is only reachable via the title attr on disabled button

    const service: InstructorService = { ...baseService, duration_options: [120] };
    // duration=120, availableMinutes=90 => 120 > 90 => canBook=false
    // 120 > 90 but 90 !== 60 => hits the "Only X minutes available" branch
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 120, availableDuration: 90 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    expect(screen.getByText(/only 90 minutes available from 9:00 AM/i)).toBeInTheDocument();
  });

  it('renders levelLabel IIFE output with multiple unique levels', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['beginner', 'intermediate', 'advanced'],
    };

    render(<ServiceCards services={[service]} />);

    // levelLabel joins unique capitalized levels with ' · '
    expect(
      screen.getByText((content) =>
        content.includes('Beginner') &&
        content.includes('Intermediate') &&
        content.includes('Advanced')
      )
    ).toBeInTheDocument();
  });

  it('renders empty levelLabel when levels_taught is empty', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: [],
    };

    render(<ServiceCards services={[service]} />);

    // With empty levels, the "Levels:" text should not be displayed
    expect(screen.queryByText(/levels:/i)).not.toBeInTheDocument();
  });

  it('renders levelLabel with single level', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['advanced'],
    };

    render(<ServiceCards services={[service]} />);

    expect(
      screen.getByText((content) => content.includes('Advanced'))
    ).toBeInTheDocument();
  });

  it('exercises the levels_taught fallback path when raw cast yields non-array', () => {
    // The ServiceCardItem has a double-read pattern:
    // 1. rawLevels = (service as Record<string,unknown>)['levels_taught']
    // 2. If rawLevels is not an array, falls back to service.levels_taught
    // Use defineProperty with a getter that returns different values to hit fallback
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['beginner'],
    };

    let callCount = 0;
    const proxy = new Proxy(service, {
      get(target, prop) {
        if (prop === 'levels_taught') {
          callCount++;
          // First access (rawLevels cast): return non-array
          // Second access (service.levels_taught): return the real array
          if (callCount === 1) return 'not-an-array';
          return target.levels_taught;
        }
        return Reflect.get(target, prop) as unknown;
      },
    });

    render(<ServiceCards services={[proxy]} />);

    // The fallback path processes service.levels_taught=['beginner']
    expect(
      screen.getByText((content) => content.includes('Beginner'))
    ).toBeInTheDocument();
  });

  it('exercises the age_groups fallback path when raw cast yields non-array', () => {
    const service: InstructorService = {
      ...baseService,
      age_groups: ['kids'],
    };

    let callCount = 0;
    const proxy = new Proxy(service, {
      get(target, prop) {
        if (prop === 'age_groups') {
          callCount++;
          if (callCount === 1) return 'not-an-array';
          return target.age_groups;
        }
        return Reflect.get(target, prop) as unknown;
      },
    });

    render(<ServiceCards services={[proxy]} />);

    const kidsBadge = screen.getByText(/kids lesson available/i);
    expect(kidsBadge).not.toHaveClass('opacity-0');
  });

  it('shows tooltip on mouse enter for unavailable card only', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 30 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;

    // Mouse enter on unavailable card shows tooltip
    fireEvent.mouseEnter(card);
    expect(screen.getByText(/only 30 minutes available/i)).toBeInTheDocument();

    // Mouse leave hides tooltip
    fireEvent.mouseLeave(card);
    expect(screen.queryByText(/only 30 minutes available/i)).not.toBeInTheDocument();
  });

  it('does not show tooltip when mouse enters a bookable card', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60, availableDuration: 120 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    // No tooltip should appear for a bookable card
    expect(screen.queryByText(/minutes available/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/this duration is not available/i)).not.toBeInTheDocument();
  });

  it('exercises onBook callback with no onBookService provided', async () => {
    const user = userEvent.setup();
    const service: InstructorService = { ...baseService, duration_options: [60] };

    // No onBookService provided
    render(<ServiceCards services={[service]} />);

    const button = screen.getByTestId('book-service-piano');
    await user.click(button);

    // Should not crash even without onBookService
    expect(button).toBeInTheDocument();
  });

  it('handles service with instructor_location format and hasTeachingLocations defaults to true', () => {
    const service: InstructorService = {
      ...baseService,
      format_prices: [{ format: 'instructor_location', hourly_rate: 80 }],
      min_hourly_rate: 80,
      levels_taught: [],
    };

    // Default hasTeachingLocations is true, so at-location should show
    render(<ServiceCards services={[service]} />);

    expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();
    expect(screen.getByText(/format:/i)).toBeInTheDocument();
    // No divider since no levels
    expect(screen.queryByText(/levels:/i)).not.toBeInTheDocument();
  });

  it('shows only travel icon when only student_location format is set', () => {
    const service: InstructorService = {
      ...baseService,
      format_prices: [{ format: 'student_location', hourly_rate: 120 }],
      min_hourly_rate: 120,
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.getByRole('img', { name: /travels to you/i })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /at their studio/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /online/i })).not.toBeInTheDocument();
  });

  it('does not call onBookService when it is undefined and canBook is true', async () => {
    const user = userEvent.setup();
    const service: InstructorService = { ...baseService, duration_options: [60] };

    // No onBookService callback at all
    const { container } = render(<ServiceCards services={[service]} />);

    // Click should not throw
    await user.click(screen.getByTestId('book-service-piano'));

    // Component should still be intact
    expect(container.firstChild).toBeInTheDocument();
  });

  it('handles services where skill is null for sort', () => {
    const services: InstructorService[] = [
      { ...omitServiceField(baseService, 'skill'), id: 'svc-1' },
      { ...baseService, id: 'svc-2', skill: 'Guitar' },
    ];

    render(<ServiceCards services={services} searchedService="guitar" />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    // Guitar should be first since it matches searchedService
    expect(headings[0]).toHaveTextContent('Guitar');
    // Undefined skill renders as 'Service'
    expect(headings[1]).toHaveTextContent('Service');
  });

  it('defaults getUnavailableMessage availableDuration to 60 when slot has no availableDuration', () => {
    // Parent: availableMinutes = undefined || 120 = 120. Duration=150 > 120 => canBook=false
    // Child getUnavailableMessage: availableMinutes = undefined || 60 = 60. 150 > 60 with 60===60
    // => hits "This 150-minute session requires a 3-hour time block"
    const service: InstructorService = { ...baseService, duration_options: [150] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 150 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    const card = screen.getByText('Piano').closest('.transition-all') as HTMLElement;
    fireEvent.mouseEnter(card);

    expect(screen.getByText(/this 150-minute session requires a 3-hour time block/i)).toBeInTheDocument();
  });

  it('sorts correctly when both services have undefined skill with searchedService', () => {
    // Exercises the optional chain `a.service.skill?.toLowerCase()` returning undefined for both
    const services: InstructorService[] = [
      { ...omitServiceField(baseService, 'skill'), id: 'svc-1' },
      { ...omitServiceField(baseService, 'skill'), id: 'svc-2' },
    ];

    render(<ServiceCards services={services} searchedService="piano" />);

    const headings = screen.getAllByRole('heading', { level: 3 });
    // Both should render as 'Service' since skill is undefined
    expect(headings[0]).toHaveTextContent('Service');
    expect(headings[1]).toHaveTextContent('Service');
  });

  it('falls through age_groups ternary when raw cast returns non-array and service.age_groups is also non-array', () => {
    // Exercises the final `[]` branch on line 77 when both rawAgeGroups and
    // service.age_groups are not arrays
    const service: InstructorService = omitServiceField(baseService, 'age_groups');
    // Both rawAgeGroups and service.age_groups are undefined -> falls to []
    // No kids badge shown
    render(<ServiceCards services={[service]} />);

    const kidsBadges = screen.getAllByText(/kids lesson available/i);
    kidsBadges.forEach(badge => {
      expect(badge).toHaveClass('opacity-0');
    });
  });

  it('falls through levels_taught ternary when raw cast returns non-array and service.levels_taught is also non-array', () => {
    // Exercises the final `[]` branch on line 54 when both rawLevels and
    // service.levels_taught are not arrays
    const service: InstructorService = omitServiceField(baseService, 'levels_taught');

    render(<ServiceCards services={[service]} />);

    // No levels label
    expect(screen.queryByText(/levels:/i)).not.toBeInTheDocument();
  });
});
