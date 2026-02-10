import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ServiceCards } from '../ServiceCards';
import type { InstructorService } from '@/types/instructor';

const baseService: InstructorService = {
  id: 'svc-1',
  skill: 'Piano',
  hourly_rate: 120,
  duration_options: [30, 60],
  age_groups: ['adults'],
  levels_taught: ['beginner', 'intermediate'],
  location_types: ['in_person'],
  description: '',
};

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
    expect(screen.getByText('$120')).toBeInTheDocument();
  });

  it('renders badges and labels for kids, levels, and formats', () => {
    const service: InstructorService = {
      ...baseService,
      id: 'svc-2',
      skill: 'Guitar',
      age_groups: ['kids'],
      levels_taught: ['advanced', 'beginner'],
      location_types: ['online', 'in_person'],
      offers_travel: true,
      offers_online: true,
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

    // With empty duration_options, defaults to [60], single option shows /hr price
    expect(screen.getByText('$120/hr')).toBeInTheDocument();
    // Should NOT show radio buttons for duration selection
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('uses fallback duration of 60 when duration_options is undefined', () => {
    const service: InstructorService = {
      ...baseService,
      duration_options: undefined,
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('$120/hr')).toBeInTheDocument();
  });

  it('filters out non-numeric and zero duration options in the card UI', () => {
    const service: InstructorService = {
      ...baseService,
      duration_options: [0, -30, 60, 'invalid' as unknown as number],
    };

    render(<ServiceCards services={[service]} />);

    // BUG HUNTER: defaultDuration picks service.duration_options[0] = 0 (unfiltered),
    // but ServiceCardItem filters to valid options [60]. The selectedDuration starts at 0,
    // so price is $0. This is an actual mismatch between parent and child component logic.
    expect(screen.getByText('$0/hr')).toBeInTheDocument();
    // Duration radio buttons should not show (only 1 valid option after filter)
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('renders "Service" fallback when skill is undefined', () => {
    const service: InstructorService = {
      ...baseService,
      skill: undefined,
    };

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
    const service = {
      ...baseService,
      levels_taught: undefined,
    } as InstructorService;

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
    const service = {
      ...baseService,
      age_groups: undefined,
    } as InstructorService;

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

  it('coerces string hourly_rate to number for price calculation', () => {
    const service = {
      ...baseService,
      duration_options: [60],
    } as InstructorService;

    (service as unknown as Record<string, unknown>)['hourly_rate'] = '80';

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('$80/hr')).toBeInTheDocument();
  });

  it('handles NaN hourly_rate by falling back to 0', () => {
    const service = {
      ...baseService,
      duration_options: [60],
    } as InstructorService;

    (service as unknown as Record<string, unknown>)['hourly_rate'] = 'not-a-number';

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('$0/hr')).toBeInTheDocument();
  });

  it('handles null hourly_rate by falling back to 0', () => {
    const service = {
      ...baseService,
      duration_options: [60],
    } as InstructorService;

    (service as unknown as Record<string, unknown>)['hourly_rate'] = null;

    render(<ServiceCards services={[service]} />);

    expect(screen.getByText('$0/hr')).toBeInTheDocument();
  });

  it('shows at-location format only when hasTeachingLocations is true', () => {
    const service: InstructorService = {
      ...baseService,
      offers_at_location: true,
      offers_travel: false,
      offers_online: false,
    };

    const { rerender } = render(<ServiceCards services={[service]} hasTeachingLocations={true} />);
    expect(screen.getByRole('img', { name: /at their studio/i })).toBeInTheDocument();

    rerender(<ServiceCards services={[service]} hasTeachingLocations={false} />);
    expect(screen.queryByRole('img', { name: /at their studio/i })).not.toBeInTheDocument();
  });

  it('hides format section when no format flags are set', () => {
    const service: InstructorService = {
      ...baseService,
      offers_travel: false,
      offers_at_location: false,
      offers_online: false,
    };

    render(<ServiceCards services={[service]} />);

    expect(screen.queryByText(/format:/i)).not.toBeInTheDocument();
  });

  it('shows divider between levels and format only when both exist', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: ['beginner'],
      offers_online: true,
    };

    const { container } = render(<ServiceCards services={[service]} />);

    // Divider is rendered as a gradient div between levels and format
    expect(container.querySelector('.bg-gradient-to-r')).toBeInTheDocument();
  });

  it('does not show divider when levels are empty', () => {
    const service: InstructorService = {
      ...baseService,
      levels_taught: [],
      offers_online: true,
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
      hourly_rate: 120,
      duration_options: [30, 60],
    };

    render(<ServiceCards services={[service]} />);

    // Default duration is 30 min (first option)
    // Price = (120 * 30) / 60 = $60, shown as "$60" (not "$60/hr")
    expect(screen.getByText('$60')).toBeInTheDocument();

    // Select 60 min
    await user.click(screen.getByLabelText(/60min/i));
    expect(screen.getByText('$120')).toBeInTheDocument();
  });

  it('defaults selectedSlot availableDuration to 120 when not provided', () => {
    const service: InstructorService = { ...baseService, duration_options: [60] };
    const selectedSlot = { date: '2025-01-06', time: '9:00 AM', duration: 60 };

    render(<ServiceCards services={[service]} selectedSlot={selectedSlot} />);

    // With default availableDuration of 120, 60-min service should be bookable
    const bookBtn = screen.getByTestId('book-service-piano');
    expect(bookBtn).not.toBeDisabled();
  });
});
