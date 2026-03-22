import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import InteractiveGrid from '../InteractiveGrid';
import type { WeekBits, WeekDateInfo, DayOfWeek, WeekTags } from '@/types/availability';
import type { BookedSlotPreview } from '@/types/booking';
import {
  BYTES_PER_DAY,
  BITS_PER_CELL,
  newEmptyTags,
  setRangeTag,
  TAG_NONE,
  TAG_NO_TRAVEL,
  TAG_ONLINE_ONLY,
} from '@/lib/calendar/bitset';

jest.mock('clsx', () => ({
  __esModule: true,
  default: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

function makeCellBits(bitmapStart: number): Uint8Array {
  const bits = new Uint8Array(BYTES_PER_DAY);
  for (let i = 0; i < BITS_PER_CELL; i += 1) {
    const slot = bitmapStart + i;
    const byteIdx = Math.floor(slot / 8);
    const bitIdx = slot % 8;
    bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
  }
  return bits;
}

function makeCellTags(
  bitmapStart: number,
  tag: typeof TAG_NONE | typeof TAG_ONLINE_ONLY | typeof TAG_NO_TRAVEL
): Uint8Array {
  return setRangeTag(newEmptyTags(), bitmapStart, BITS_PER_CELL, tag);
}

describe('InteractiveGrid', () => {
  const dayNames: DayOfWeek[] = [
    'sunday',
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
  ];

  const createWeekDates = (startDate: Date): WeekDateInfo[] => {
    const dates: WeekDateInfo[] = [];
    for (let i = 0; i < 7; i += 1) {
      const date = new Date(startDate);
      date.setDate(date.getDate() + i);
      dates.push({
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: dayNames[date.getDay()] as DayOfWeek,
        fullDate: date.toISOString().slice(0, 10),
      });
    }
    return dates;
  };

  const futureMonday = new Date('2030-01-07T00:00:00Z');
  const mockWeekDates = createWeekDates(futureMonday);

  const defaultProps = {
    weekDates: mockWeekDates,
    weekBits: {} as WeekBits,
    onBitsChange: jest.fn(),
    allowPastEditing: true,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2030-01-08T10:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('rendering', () => {
    it('renders availability cells for each day', () => {
      render(<InteractiveGrid {...defaultProps} />);

      expect(screen.getAllByTestId('availability-cell').length).toBeGreaterThan(0);
    });

    it('renders time labels and day headers', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      expect(screen.getByText((content) => content.includes('9:00'))).toBeInTheDocument();
      expect(screen.getByText('MON')).toBeInTheDocument();
      expect(screen.getByText('TUE')).toBeInTheDocument();
    });

    it('respects custom hour ranges and extended midnight labels', () => {
      render(<InteractiveGrid {...defaultProps} startHour={22} endHour={24} />);

      expect(screen.getByText((content) => content.includes('10:00 PM'))).toBeInTheDocument();
      expect(screen.getByText((content) => content.includes('11:00 PM'))).toBeInTheDocument();
    });

    it('renders the +1 day midnight label when the window crosses past 24:00', () => {
      render(<InteractiveGrid {...defaultProps} startHour={24} endHour={25} />);

      expect(screen.getByText((content) => content.includes('12:00 AM (+1d)'))).toBeInTheDocument();
    });

    it('uses local time when no timezone prop is provided', () => {
      render(<InteractiveGrid {...defaultProps} />);

      expect(screen.getByRole('grid')).toBeInTheDocument();
    });

    it('supports timezone-aware rendering and empty mobile week data', () => {
      const { rerender } = render(<InteractiveGrid {...defaultProps} timezone="UTC" />);

      expect(screen.getByRole('grid')).toBeInTheDocument();

      rerender(
        <InteractiveGrid
          {...defaultProps}
          weekDates={[]}
          weekBits={{}}
          isMobile={true}
          activeDayIndex={0}
        />
      );

      expect(screen.getByRole('grid')).toBeInTheDocument();
    });
  });

  describe('painting behavior', () => {
    const PaintWrapper = ({
      initialBits,
      initialTags,
      paintMode = TAG_NONE,
      bookedSlots = [],
      allowPastEditing = true,
      availableTagOptions = [TAG_ONLINE_ONLY, TAG_NO_TRAVEL] as const,
      isMobile = false,
      activeDayIndex = 0,
    }: {
      initialBits?: WeekBits;
      initialTags?: WeekTags;
      paintMode?: typeof TAG_NONE | typeof TAG_ONLINE_ONLY | typeof TAG_NO_TRAVEL;
      bookedSlots?: BookedSlotPreview[];
      allowPastEditing?: boolean;
      availableTagOptions?: readonly (typeof TAG_ONLINE_ONLY | typeof TAG_NO_TRAVEL)[];
      isMobile?: boolean;
      activeDayIndex?: number;
    }) => {
      const [bits, setBits] = React.useState<WeekBits>(
        initialBits ?? {
          '2030-01-07': makeCellBits(108),
        }
      );
      const [tags, setTags] = React.useState<WeekTags>(initialTags ?? {});

      return (
        <InteractiveGrid
          {...defaultProps}
          weekBits={bits}
          weekTags={tags}
          onBitsChange={setBits}
          onTagsChange={setTags}
          paintMode={paintMode}
          availableTagOptions={[...availableTagOptions]}
          bookedSlots={bookedSlots}
          startHour={9}
          endHour={10}
          allowPastEditing={allowPastEditing}
          isMobile={isMobile}
          activeDayIndex={activeDayIndex}
        />
      );
    };

    it('uses normal availability painting when no tag options are available', () => {
      render(
        <PaintWrapper
          initialBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          availableTagOptions={[]}
          paintMode={TAG_ONLINE_ONLY}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.mouseDown(firstCell!, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell!, { button: 0 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
    });

    it('applies the online-only brush on click', () => {
      render(
        <PaintWrapper
          initialBits={{ '2030-01-10': makeCellBits(108) }}
          paintMode={TAG_ONLINE_ONLY}
        />
      );

      const targetCell = screen.getByRole('gridcell', { name: /Thursday 09:00/ });
      fireEvent.mouseDown(targetCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(targetCell, { button: 0 });

      expect(targetCell).toHaveAttribute('data-tag-state', 'online_only');
      expect(screen.getByTestId('tag-indicator-online')).toBeInTheDocument();
    });

    it('applies the no-travel brush across a dragged range', () => {
      render(
        <PaintWrapper
          initialBits={{
            '2030-01-07': (() => {
              const bits = makeCellBits(108);
              for (let i = 0; i < BITS_PER_CELL; i += 1) {
                const slot = 114 + i;
                const byteIdx = Math.floor(slot / 8);
                const bitIdx = slot % 8;
                bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
              }
              return bits;
            })(),
          }}
          paintMode={TAG_NO_TRAVEL}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseDown(cells[0]!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(cells[7]!, { buttons: 1 });
      fireEvent.mouseUp(cells[7]!, { button: 0 });

      expect(cells[0]).toHaveAttribute('data-tag-state', 'no_travel');
      expect(cells[7]).toHaveAttribute('data-tag-state', 'no_travel');
      expect(screen.getAllByTestId('tag-indicator-no-travel-slash').length).toBeGreaterThan(0);
    });

    it('clears a matching brush tag back to all formats while keeping the cell selected', () => {
      render(
        <PaintWrapper
          initialTags={{ '2030-01-07': makeCellTags(108, TAG_ONLINE_ONLY) }}
          paintMode={TAG_ONLINE_ONLY}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
    });

    it('turns selected cells off and clears tags in all-formats mode', () => {
      render(
        <PaintWrapper
          initialBits={{
            '2030-01-07': (() => {
              const bits = makeCellBits(108);
              for (let i = 0; i < BITS_PER_CELL; i += 1) {
                const slot = 114 + i;
                const byteIdx = Math.floor(slot / 8);
                const bitIdx = slot % 8;
                bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
              }
              return bits;
            })(),
          }}
          initialTags={{
            '2030-01-07': (() => {
              let tags = makeCellTags(108, TAG_NO_TRAVEL);
              tags = setRangeTag(tags, 114, BITS_PER_CELL, TAG_NO_TRAVEL);
              return tags;
            })(),
          }}
          paintMode={TAG_NONE}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseDown(cells[0]!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(cells[7]!, { buttons: 1 });
      fireEvent.mouseUp(cells[7]!, { button: 0 });

      expect(cells[0]).toHaveAttribute('data-tag-state', 'inactive');
      expect(cells[7]).toHaveAttribute('data-tag-state', 'inactive');
    });

    it('skips tag updates when no tag updater is provided', () => {
      const WithoutTagUpdater = () => {
        const [bits, setBits] = React.useState<WeekBits>({});

        return (
          <InteractiveGrid
            {...defaultProps}
            weekBits={bits}
            weekTags={{}}
            onBitsChange={setBits}
            availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
            paintMode={TAG_NO_TRAVEL}
            startHour={9}
            endHour={10}
          />
        );
      };

      render(<WithoutTagUpdater />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
    });

    it('returns early when clearing a tag without a tag updater', () => {
      const WithoutTagUpdater = () => {
        const [bits] = React.useState<WeekBits>({ '2030-01-07': makeCellBits(108) });

        return (
          <InteractiveGrid
            {...defaultProps}
            weekBits={bits}
            weekTags={{ '2030-01-07': makeCellTags(108, TAG_ONLINE_ONLY) }}
            onBitsChange={jest.fn()}
            availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
            paintMode={TAG_ONLINE_ONLY}
            startHour={9}
            endHour={10}
          />
        );
      };

      render(<WithoutTagUpdater />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(firstCell).toHaveAttribute('data-tag-state', 'online_only');
    });

    it('executes the toggle updater body against the latest previous bits', () => {
      const onBitsChange = jest.fn();

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      const updater = onBitsChange.mock.calls[0]?.[0] as ((prev: WeekBits) => WeekBits) | undefined;
      expect(updater).toBeDefined();

      const next = updater?.({ '2030-01-07': new Uint8Array(BYTES_PER_DAY) });
      expect(next?.['2030-01-07']).toBeDefined();
    });

    it('executes the clear-tag updater body against existing tags', () => {
      const onTagsChange = jest.fn();

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': makeCellBits(108) }}
          weekTags={{ '2030-01-07': makeCellTags(108, TAG_ONLINE_ONLY) }}
          onBitsChange={jest.fn()}
          onTagsChange={onTagsChange}
          availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
          paintMode={TAG_ONLINE_ONLY}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      const updater = onTagsChange.mock.calls[0]?.[0] as ((prev: WeekTags) => WeekTags) | undefined;
      expect(updater).toBeDefined();

      const next = updater?.({ '2030-01-07': makeCellTags(108, TAG_ONLINE_ONLY) });
      expect(next?.['2030-01-07']).toBeDefined();
    });

    it('renders mixed tag cells with the base active palette', () => {
      const mixedTags = setRangeTag(newEmptyTags(), 108, 3, TAG_ONLINE_ONLY);

      render(
        <PaintWrapper
          initialTags={{ '2030-01-07': mixedTags }}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      expect(firstCell).toHaveAttribute('data-tag-state', 'mixed');
      expect(firstCell.className).toContain('bg-[#EDE3FA]');
    });

    it('shows saved tag visuals on past cells while keeping them locked', () => {
      render(
        <PaintWrapper
          initialTags={{ '2030-01-07': makeCellTags(108, TAG_NO_TRAVEL) }}
          paintMode={TAG_NONE}
          allowPastEditing={false}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      expect(firstCell).toHaveAttribute('data-tag-state', 'no_travel');
      expect(screen.getByTestId('tag-indicator-no-travel')).toBeInTheDocument();

      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(firstCell).toHaveAttribute('data-tag-state', 'no_travel');
    });

    it('allows clicking booked cells to toggle availability while preserving the booked overlay', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:00:00',
          end_time: '09:30:00',
          student_first_name: 'John',
          student_last_initial: 'D.',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 30,
          location_type: 'student_location',
        },
      ];

      render(
        <PaintWrapper
          initialBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          bookedSlots={bookedSlots}
          paintMode={TAG_NONE}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      expect(firstCell.querySelector('span[class*="repeating-linear-gradient"]')).toBeInTheDocument();

      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
      expect(firstCell.querySelector('span[class*="repeating-linear-gradient"]')).toBeInTheDocument();
    });

    it('keeps right click as a no-op for tag editing', () => {
      render(<PaintWrapper />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.contextMenu(firstCell);

      expect(screen.queryByRole('radio', { name: /Online Only/i })).not.toBeInTheDocument();
    });

    it('keeps already-selected cells on while dragging from an empty cell in all-formats mode', () => {
      render(
        <PaintWrapper
          initialBits={{
            '2030-01-07': (() => {
              const bits = makeCellBits(114);
              for (let i = 0; i < BITS_PER_CELL; i += 1) {
                const slot = 108 + i;
                const byteIdx = Math.floor(slot / 8);
                const bitIdx = slot % 8;
                bits[byteIdx] = (bits[byteIdx] ?? 0) & ~(1 << bitIdx);
              }
              return bits;
            })(),
          }}
          paintMode={TAG_NONE}
        />
      );

      const mondayNine = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      const mondayNineThirty = screen.getByRole('gridcell', { name: /Monday 09:30/ });
      fireEvent.mouseDown(mondayNine, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(mondayNineThirty, { buttons: 1 });
      fireEvent.mouseUp(mondayNineThirty, { button: 0 });

      expect(mondayNine).toHaveAttribute('aria-selected', 'true');
      expect(mondayNineThirty).toHaveAttribute('aria-selected', 'true');
    });

    it('skips duplicate toggle updaters when the same empty cell is entered twice before rerender', () => {
      let bitsState: WeekBits = { '2030-01-07': new Uint8Array(BYTES_PER_DAY) };
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        bitsState = typeof next === 'function' ? next(bitsState) : next;
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(firstCell, { buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(onBitsChange).toHaveBeenCalledTimes(2);
      expect(bitsState['2030-01-07']).toBeDefined();
      expect(bitsState['2030-01-07']).not.toEqual(new Uint8Array(BYTES_PER_DAY));
    });

    it('skips duplicate tag paints when the same cell is entered twice before state sync', () => {
      let bitsState: WeekBits = { '2030-01-07': new Uint8Array(BYTES_PER_DAY) };
      let tagsState: WeekTags = { '2030-01-07': newEmptyTags() };
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        bitsState = typeof next === 'function' ? next(bitsState) : next;
      });
      const onTagsChange = jest.fn((next: WeekTags | ((prev: WeekTags) => WeekTags)) => {
        tagsState = typeof next === 'function' ? next(tagsState) : next;
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          weekTags={{ '2030-01-07': newEmptyTags() }}
          onBitsChange={onBitsChange}
          onTagsChange={onTagsChange}
          availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
          paintMode={TAG_NO_TRAVEL}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.mouseDown(firstCell, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(firstCell, { buttons: 1 });
      fireEvent.mouseUp(firstCell, { button: 0 });

      expect(onBitsChange).toHaveBeenCalledTimes(2);
      expect(onTagsChange).toHaveBeenCalledTimes(2);
      expect(tagsState['2030-01-07']).toBeDefined();
    });

    it('skips duplicate toggle paints while dragging over already-selected cells', () => {
      render(
        <PaintWrapper
          initialBits={{
            '2030-01-07': (() => {
              let bits = new Uint8Array(BYTES_PER_DAY);
              for (let i = 0; i < BITS_PER_CELL; i += 1) {
                const slot = 114 + i;
                const byteIdx = Math.floor(slot / 8);
                const bitIdx = slot % 8;
                bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
              }
              return bits;
            })(),
          }}
          paintMode={TAG_NONE}
        />
      );

      const mondayNine = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      const mondayNineThirty = screen.getByRole('gridcell', { name: /Monday 09:30/ });
      fireEvent.mouseDown(mondayNine, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(mondayNine, { buttons: 1 });
      fireEvent.mouseEnter(mondayNineThirty, { buttons: 1 });
      fireEvent.mouseUp(mondayNineThirty, { button: 0 });

      expect(mondayNine).toHaveAttribute('aria-selected', 'true');
      expect(mondayNineThirty).toHaveAttribute('aria-selected', 'true');
    });
  });

  describe('keyboard interaction', () => {
    it('uses the active brush on Enter', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': makeCellBits(108) }}
          weekTags={{}}
          onBitsChange={jest.fn()}
          onTagsChange={jest.fn()}
          availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
          paintMode={TAG_ONLINE_ONLY}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.keyDown(firstCell, { key: 'Enter' });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
    });

    it('uses the active brush on Space', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.keyDown(firstCell, { key: ' ' });

      expect(defaultProps.onBitsChange).toHaveBeenCalled();
    });

    it('does not apply keyboard painting on locked cells', () => {
      const onBitsChange = jest.fn();

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          allowPastEditing={false}
          startHour={9}
          endHour={10}
        />
      );

      const pastCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.keyDown(pastCell, { key: 'Enter' });

      expect(onBitsChange).not.toHaveBeenCalled();
    });

    it('does not toggle on unrelated keys', () => {
      const onBitsChange = jest.fn();
      render(<InteractiveGrid {...defaultProps} onBitsChange={onBitsChange} startHour={9} endHour={10} />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      fireEvent.keyDown(firstCell, { key: 'a' });

      expect(onBitsChange).not.toHaveBeenCalled();
    });

    it('moves focus with arrow keys and row boundary keys', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      const firstCell = document.querySelector<HTMLButtonElement>('[data-row-index="0"][data-col-index="0"]');
      const secondCell = document.querySelector<HTMLButtonElement>('[data-row-index="0"][data-col-index="1"]');
      const nextRowCell = document.querySelector<HTMLButtonElement>('[data-row-index="1"][data-col-index="1"]');

      firstCell!.focus();
      fireEvent.keyDown(firstCell!, { key: 'ArrowRight' });
      expect(document.activeElement).toBe(secondCell);

      fireEvent.keyDown(secondCell!, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(nextRowCell);

      fireEvent.keyDown(nextRowCell!, { key: 'Home' });
      expect(document.activeElement).toBe(
        document.querySelector<HTMLButtonElement>('[data-row-index="1"][data-col-index="0"]')
      );

      fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'End' });
      expect(document.activeElement).toBe(
        document.querySelector<HTMLButtonElement>('[data-row-index="1"][data-col-index="6"]')
      );
    });

    it('keeps focus in place at grid edges', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const firstCell = document.querySelector<HTMLButtonElement>('[data-row-index="0"][data-col-index="0"]');
      const lastCell = document.querySelector<HTMLButtonElement>('[data-row-index="1"][data-col-index="6"]');

      firstCell!.focus();
      fireEvent.keyDown(firstCell!, { key: 'ArrowLeft' });
      expect(document.activeElement).toBe(firstCell);

      lastCell!.focus();
      fireEvent.keyDown(lastCell!, { key: 'ArrowRight' });
      expect(document.activeElement).toBe(lastCell);

      firstCell!.focus();
      fireEvent.keyDown(firstCell!, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(firstCell);
    });
  });

  describe('drag selection', () => {
    const DragWrapper = ({
      initialBits = {
        '2030-01-07': new Uint8Array(BYTES_PER_DAY),
        '2030-01-08': new Uint8Array(BYTES_PER_DAY),
      } as WeekBits,
      startHour = 9,
      endHour = 10,
    }: {
      initialBits?: WeekBits;
      startHour?: number;
      endHour?: number;
    }) => {
      const [bits, setBits] = React.useState<WeekBits>(initialBits);

      return (
        <InteractiveGrid
          {...defaultProps}
          weekBits={bits}
          onBitsChange={setBits}
          startHour={startHour}
          endHour={endHour}
        />
      );
    };

    it('supports drag to select multiple cells', () => {
      render(
        <DragWrapper initialBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }} />
      );

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseDown(cells[0]!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(cells[7]!, { buttons: 1 });
      fireEvent.mouseUp(cells[7]!, { button: 0 });

      expect(cells[0]).toHaveAttribute('aria-selected', 'true');
      expect(cells[7]).toHaveAttribute('aria-selected', 'true');
    });

    it('handles drag across different date columns', () => {
      render(<DragWrapper />);

      const mondayCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      const tuesdayCell = screen.getByRole('gridcell', { name: /Tuesday 09:00/ });

      fireEvent.mouseDown(mondayCell, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(tuesdayCell, { buttons: 1 });
      fireEvent.mouseUp(tuesdayCell, { button: 0 });

      expect(mondayCell).toHaveAttribute('aria-selected', 'true');
      expect(tuesdayCell).toHaveAttribute('aria-selected', 'true');
    });

    it('interpolates rows when dragging vertically in both directions', () => {
      render(
        <DragWrapper
          initialBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          startHour={9}
          endHour={11}
        />
      );

      const topCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      const lowerCell = screen.getByRole('gridcell', { name: /Monday 10:30/ });

      fireEvent.mouseDown(topCell, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(lowerCell, { buttons: 1 });
      fireEvent.mouseUp(lowerCell, { button: 0 });

      expect(screen.getByRole('gridcell', { name: /Monday 09:30/ })).toHaveAttribute(
        'aria-selected',
        'true'
      );
      expect(screen.getByRole('gridcell', { name: /Monday 10:00/ })).toHaveAttribute(
        'aria-selected',
        'true'
      );

      fireEvent.mouseDown(lowerCell, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(topCell, { buttons: 1 });
      fireEvent.mouseUp(topCell, { button: 0 });

      expect(topCell).toHaveAttribute('aria-selected', 'false');
    });

    it('does not continue painting when mouse buttons are not held', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseEnter(cells[7]!, { buttons: 0 });

      expect(cells[7]).toHaveAttribute('aria-selected', 'false');
    });

    it('finishes drag on mouse leave when no button is held', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': new Uint8Array(BYTES_PER_DAY) }}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseDown(cells[0]!, { button: 0, buttons: 1 });
      fireEvent.mouseLeave(cells[0]!, { buttons: 0 });
      fireEvent.mouseEnter(cells[7]!, { buttons: 0 });

      expect(cells[7]).toHaveAttribute('aria-selected', 'false');
    });
  });

  describe('booked, mobile, and accessibility states', () => {
    it('shows booked overlays', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:00:00',
          end_time: '09:30:00',
          student_first_name: 'John',
          student_last_initial: 'D.',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 30,
          location_type: 'student_location',
        },
      ];

      render(<InteractiveGrid {...defaultProps} bookedSlots={bookedSlots} startHour={9} endHour={10} />);

      const firstCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      expect(firstCell.querySelector('span')).toBeInTheDocument();
    });

    it('renders a single day in mobile view and respects activeDayIndex', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={2}
          startHour={9}
          endHour={10}
        />
      );

      expect(screen.queryByText('MON')).not.toBeInTheDocument();
      expect(screen.getByText('WED')).toBeInTheDocument();
    });

    it('handles out-of-range mobile activeDayIndex by falling back to the first day', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={99}
          startHour={9}
          endHour={10}
        />
      );

      expect(screen.getByText('MON')).toBeInTheDocument();
    });

    it('marks past slots as disabled and allows editing when configured', () => {
      const { rerender } = render(
        <InteractiveGrid
          {...defaultProps}
          allowPastEditing={false}
          startHour={9}
          endHour={10}
        />
      );

      const pastCell = screen.getByRole('gridcell', { name: /Monday 09:00/ });
      expect(pastCell).toHaveAttribute('aria-disabled', 'true');

      rerender(
        <InteractiveGrid
          {...defaultProps}
          allowPastEditing={true}
          startHour={9}
          endHour={10}
        />
      );
      expect(screen.getByRole('gridcell', { name: /Monday 09:00/ })).toHaveAttribute(
        'aria-disabled',
        'false'
      );
    });

    it('renders expected grid accessibility attributes', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      expect(screen.getByRole('grid')).toBeInTheDocument();
      expect(screen.getAllByRole('columnheader').length).toBeGreaterThan(1);
      expect(screen.getAllByRole('rowheader').length).toBeGreaterThan(0);
      expect(screen.getByRole('gridcell', { name: /Monday 09:00/ })).toHaveAttribute(
        'data-time',
        '09:00:00'
      );
    });
  });

  describe('now line', () => {
    it('shows the now line within the visible window and hides it outside', () => {
      const { rerender } = render(
        <InteractiveGrid {...defaultProps} timezone="UTC" startHour={9} endHour={11} />
      );
      expect(screen.getByTestId('now-line')).toBeInTheDocument();

      rerender(<InteractiveGrid {...defaultProps} timezone="UTC" startHour={12} endHour={13} />);
      expect(screen.queryByTestId('now-line')).not.toBeInTheDocument();
    });
  });
});
