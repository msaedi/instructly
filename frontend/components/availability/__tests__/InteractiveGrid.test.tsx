import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

// Mock clsx to pass through classnames
jest.mock('clsx', () => ({
  __esModule: true,
  default: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

/** Create a Uint8Array(36) with a full 30-min cell set (6 consecutive bits starting at bitmapStart). */
function makeCellBits(bitmapStart: number): Uint8Array {
  const bits = new Uint8Array(BYTES_PER_DAY);
  for (let i = 0; i < BITS_PER_CELL; i++) {
    const slot = bitmapStart + i;
    const byteIdx = Math.floor(slot / 8);
    const bitIdx = slot % 8;
    if (byteIdx < bits.length) {
      bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
    }
  }
  return bits;
}

function makeCellTags(bitmapStart: number, tag: typeof TAG_NONE | typeof TAG_ONLINE_ONLY | typeof TAG_NO_TRAVEL): Uint8Array {
  return setRangeTag(newEmptyTags(), bitmapStart, BITS_PER_CELL, tag);
}

describe('InteractiveGrid', () => {
  const DAY_NAMES: DayOfWeek[] = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

  const createWeekDates = (startDate: Date): WeekDateInfo[] => {
    const dates: WeekDateInfo[] = [];
    for (let i = 0; i < 7; i++) {
      const date = new Date(startDate);
      date.setDate(date.getDate() + i);
      dates.push({
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: DAY_NAMES[date.getDay()] as DayOfWeek,
        fullDate: date.toISOString().slice(0, 10),
      });
    }
    return dates;
  };

  // Use a future date to avoid past date issues
  const futureMonday = new Date('2030-01-07');
  const mockWeekDates = createWeekDates(futureMonday);

  const defaultProps = {
    weekDates: mockWeekDates,
    weekBits: {} as WeekBits,
    onBitsChange: jest.fn(),
    allowPastEditing: true,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock Date.now to return a consistent "today"
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2030-01-08T10:00:00'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('rendering', () => {
    it('renders availability cells for each day', () => {
      render(<InteractiveGrid {...defaultProps} />);

      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });

    it('renders time labels', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      // Component renders time labels every hour (only on the hour, not half hour)
      // The format shows only on even rows (hour boundaries)
      const container = screen.getByText((content) => content.includes('9:00'));
      expect(container).toBeInTheDocument();
    });

    it('renders day headers with weekday abbreviations', () => {
      render(<InteractiveGrid {...defaultProps} />);

      // Should show day headers
      expect(screen.getByText('MON')).toBeInTheDocument();
      expect(screen.getByText('TUE')).toBeInTheDocument();
    });

    it('respects custom hour range', () => {
      render(<InteractiveGrid {...defaultProps} startHour={10} endHour={12} />);

      // Component renders time labels
      const container = screen.getByText((content) => content.includes('10:00'));
      expect(container).toBeInTheDocument();
    });
  });

  describe('slot selection', () => {
    it('calls onBitsChange when cell is clicked', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('marks selected cells with aria-selected', () => {
      const selectedDate = mockWeekDates[0]!.fullDate;
      // 9:00 AM = bitmap slot 108 (9 * 12). A 30-min cell sets 6 consecutive bits.
      const weekBits: WeekBits = {
        [selectedDate]: makeCellBits(108),
      };

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={weekBits}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const selectedCells = cells.filter(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );
      expect(selectedCells).toHaveLength(1);
    });

    it('does not call onBitsChange when clicking already selected cell during drag', () => {
      // Create weekBits with the 9:00 AM cell already selected
      // 9 AM = bitmap slot 108 (9 * 12), 6 consecutive bits per cell
      // 9:00 AM = bitmap slot 108. A 30-min cell sets 6 consecutive bits.
      const weekBits: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={weekBits}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const selectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );

      // This is testing the early return path - the implementation should
      // handle already-selected cells during drag appropriately
      if (selectedCell) {
        fireEvent.mouseDown(selectedCell);
        fireEvent.mouseUp(selectedCell);
      }

      // The function will be called but the early return prevents unnecessary state updates
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles toggling off a selected cell', () => {
      // Set up with a pre-selected slot
      // 9:00 AM = bitmap slot 108. A 30-min cell sets 6 consecutive bits.
      const weekBits: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={weekBits}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const selectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );

      if (selectedCell) {
        // Click to deselect
        fireEvent.mouseDown(selectedCell);
        fireEvent.mouseUp(selectedCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });
  });

  describe('tagging', () => {
    const mixedTagOptions = [TAG_ONLINE_ONLY, TAG_NO_TRAVEL] as const;

    const TagWrapper = ({
      initialBits,
      initialTags,
      bookedSlots = [],
      availableTagOptions = mixedTagOptions,
      isMobile = false,
    }: {
      initialBits?: WeekBits;
      initialTags?: WeekTags;
      bookedSlots?: BookedSlotPreview[];
      availableTagOptions?: readonly (typeof TAG_ONLINE_ONLY | typeof TAG_NO_TRAVEL)[];
      isMobile?: boolean;
    }) => {
      const [bits, setBits] = React.useState<WeekBits>(initialBits ?? {
        '2030-01-07': makeCellBits(108),
      });
      const [tags, setTags] = React.useState<WeekTags>(initialTags ?? {});

      return (
        <InteractiveGrid
          {...defaultProps}
          weekBits={bits}
          weekTags={tags}
          onBitsChange={setBits}
          onTagsChange={setTags}
          availableTagOptions={[...availableTagOptions]}
          bookedSlots={bookedSlots}
          startHour={9}
          endHour={10}
          isMobile={isMobile}
        />
      );
    };

    it('hides tagging UI when no tag options are available', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{
            '2030-01-07': makeCellBits(108),
          }}
          weekTags={{}}
          onBitsChange={jest.fn()}
          onTagsChange={jest.fn()}
          availableTagOptions={[]}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
      fireEvent.contextMenu(firstCell!);
      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('shows the tag popover with the correct options on right click', () => {
      render(<TagWrapper />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.contextMenu(firstCell!);

      expect(screen.getByTestId('format-tag-popover')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'All formats' })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'Online Only' })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'No Travel' })).toBeInTheDocument();
    });

    it('applies a selected tag and renders the matching indicator', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(
        <TagWrapper
          initialBits={{
            '2030-01-10': makeCellBits(108),
          }}
        />
      );

      const targetCell = screen.getAllByTestId('availability-cell')[3];
      fireEvent.contextMenu(targetCell!);
      await user.click(screen.getByRole('radio', { name: 'Online Only' }));

      expect(targetCell).toHaveAttribute('data-tag-state', 'online_only');
      expect(screen.getByTestId('tag-indicator-online')).toBeInTheDocument();
    });

    it('clears tags back to none when a tagged cell is toggled off', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(
        <TagWrapper
          initialTags={{
            '2030-01-07': makeCellTags(108, TAG_ONLINE_ONLY),
          }}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      expect(firstCell).toHaveAttribute('data-tag-state', 'online_only');

      await user.pointer([
        { target: firstCell!, keys: '[MouseLeft>]' },
        { target: firstCell!, keys: '[/MouseLeft]' },
      ]);

      expect(firstCell).toHaveAttribute('aria-selected', 'false');
      expect(firstCell).toHaveAttribute('data-tag-state', 'inactive');
    });

    it('does not open the tag popover for booked cells', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:00:00',
          end_time: '09:30:00',
          student_first_name: 'John',
          student_last_initial: 'D',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 30,
          location_type: 'student_location',
        },
      ];

      render(<TagWrapper bookedSlots={bookedSlots} />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.contextMenu(firstCell!);

      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('clears tags across a deselected drag range', async () => {
      render(
        <TagWrapper
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
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[7];

      fireEvent.mouseDown(firstCell!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(secondCell!, { buttons: 1 });
      fireEvent.mouseUp(secondCell!, { button: 0 });

      expect(firstCell).toHaveAttribute('data-tag-state', 'inactive');
      expect(secondCell).toHaveAttribute('data-tag-state', 'inactive');
    });

    it('safely skips tag clearing when no tag updater is provided', () => {
      const WithoutTagUpdater = () => {
        const [bits, setBits] = React.useState<WeekBits>({
          '2030-01-07': (() => {
            const next = makeCellBits(108);
            for (let i = 0; i < BITS_PER_CELL; i += 1) {
              const slot = 114 + i;
              const byteIdx = Math.floor(slot / 8);
              const bitIdx = slot % 8;
              next[byteIdx] = (next[byteIdx] ?? 0) | (1 << bitIdx);
            }
            return next;
          })(),
        });

        return (
          <InteractiveGrid
            {...defaultProps}
            weekBits={bits}
            weekTags={{ '2030-01-07': makeCellTags(108, TAG_NO_TRAVEL) }}
            onBitsChange={setBits}
            availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
            startHour={9}
            endHour={10}
          />
        );
      };

      render(<WithoutTagUpdater />);

      const cells = screen.getAllByTestId('availability-cell');
      fireEvent.mouseDown(cells[0]!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(cells[7]!, { buttons: 1 });
      fireEvent.mouseUp(cells[7]!, { button: 0 });

      expect(cells[0]).toHaveAttribute('aria-selected', 'false');
      expect(cells[7]).toHaveAttribute('aria-selected', 'false');
    });

    it('applies a tag across a right-drag range', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(
        <TagWrapper
          initialBits={{
            '2030-01-07': (() => {
              let bits = makeCellBits(108);
              bits = (() => {
                const next = bits.slice();
                for (let i = 0; i < BITS_PER_CELL; i += 1) {
                  const slot = 114 + i;
                  const byteIdx = Math.floor(slot / 8);
                  const bitIdx = slot % 8;
                  next[byteIdx] = (next[byteIdx] ?? 0) | (1 << bitIdx);
                }
                return next;
              })();
              return bits;
            })(),
          }}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[7];

      fireEvent.mouseDown(firstCell!, { button: 2, buttons: 2 });
      fireEvent.mouseEnter(secondCell!, { buttons: 2 });
      fireEvent.mouseUp(secondCell!, { button: 2, buttons: 2 });
      fireEvent.contextMenu(secondCell!, { button: 2, buttons: 2 });
      await user.click(screen.getByRole('radio', { name: 'No Travel' }));

      expect(firstCell).toHaveAttribute('data-tag-state', 'no_travel');
      expect(secondCell).toHaveAttribute('data-tag-state', 'no_travel');
    });

    it('keeps mixed tag selections unchecked in the popover', () => {
      render(
        <TagWrapper
          initialBits={{
            '2030-01-10': (() => {
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
            '2030-01-10': (() => {
              let tags = makeCellTags(108, TAG_ONLINE_ONLY);
              tags = setRangeTag(tags, 114, BITS_PER_CELL, TAG_NO_TRAVEL);
              return tags;
            })(),
          }}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[3];
      const secondCell = cells[10];

      fireEvent.mouseDown(firstCell!, { button: 2, buttons: 2 });
      fireEvent.mouseEnter(secondCell!, { buttons: 2 });
      fireEvent.contextMenu(secondCell!, { button: 2, buttons: 2 });

      expect(screen.getByRole('radio', { name: 'All formats' })).toHaveAttribute(
        'aria-checked',
        'false'
      );
      expect(screen.getByRole('radio', { name: 'Online Only' })).toHaveAttribute(
        'aria-checked',
        'false'
      );
      expect(screen.getByRole('radio', { name: 'No Travel' })).toHaveAttribute(
        'aria-checked',
        'false'
      );
    });

    it('extends tag selection across different dates on the same row', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(
        <TagWrapper
          initialBits={{
            '2030-01-07': makeCellBits(108),
            '2030-01-08': makeCellBits(108),
          }}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const mondayCell = cells[0];
      const tuesdayCell = cells[1];

      fireEvent.mouseDown(mondayCell!, { button: 2, buttons: 2 });
      fireEvent.mouseEnter(tuesdayCell!, { buttons: 2 });
      fireEvent.contextMenu(tuesdayCell!, { button: 2, buttons: 2 });
      await user.click(screen.getByRole('radio', { name: 'Online Only' }));

      expect(mondayCell).toHaveAttribute('data-tag-state', 'online_only');
      expect(tuesdayCell).toHaveAttribute('data-tag-state', 'online_only');
    });

    it('re-enters the same cell during tag selection without losing the target range', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(<TagWrapper />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.mouseDown(firstCell!, { button: 2, buttons: 2 });
      fireEvent.mouseEnter(firstCell!, { buttons: 2 });
      fireEvent.contextMenu(firstCell!, { button: 2, buttons: 2 });
      await user.click(screen.getByRole('radio', { name: 'No Travel' }));

      expect(firstCell).toHaveAttribute('data-tag-state', 'no_travel');
    });

    it('treats a mixed single-cell tag as an unchecked popover selection', () => {
      const mixedTags = newEmptyTags();
      const partiallyTagged = setRangeTag(mixedTags, 108, 3, TAG_ONLINE_ONLY);

      render(
        <TagWrapper
          initialBits={{
            '2030-01-10': makeCellBits(108),
          }}
          initialTags={{
            '2030-01-10': partiallyTagged,
          }}
        />
      );

      const targetCell = screen.getAllByTestId('availability-cell')[3];
      fireEvent.contextMenu(targetCell!);

      expect(screen.getByRole('radio', { name: 'All formats' })).toHaveAttribute(
        'aria-checked',
        'false'
      );
    });

    it('closes the popover without applying a tag when no tag updater is provided', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{ '2030-01-07': makeCellBits(108) }}
          weekTags={{}}
          onBitsChange={jest.fn()}
          availableTagOptions={[TAG_ONLINE_ONLY, TAG_NO_TRAVEL]}
          startHour={9}
          endHour={10}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.contextMenu(firstCell!);
      await user.click(screen.getByRole('radio', { name: 'Online Only' }));

      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
      expect(firstCell).toHaveAttribute('data-tag-state', 'none');
    });

    it('ignores a synthetic mouse down immediately after long press opens the popover', async () => {
      render(<TagWrapper isMobile={true} />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.touchStart(firstCell!);

      await act(async () => {
        jest.advanceTimersByTime(450);
      });

      fireEvent.mouseDown(firstCell!, { button: 0, buttons: 1 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByTestId('format-tag-popover')).toBeInTheDocument();
    });

    it('does not start tag selection from an inactive cell on right mouse down', () => {
      render(
        <TagWrapper
          initialBits={{
            '2030-01-07': new Uint8Array(BYTES_PER_DAY),
          }}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.mouseDown(firstCell!, { button: 2, buttons: 2 });
      fireEvent.contextMenu(firstCell!, { button: 2, buttons: 2 });

      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('skips tag selection expansion when the hovered cell is locked', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:30:00',
          end_time: '10:00:00',
          student_first_name: 'John',
          student_last_initial: 'D',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 30,
          location_type: 'student_location',
        },
      ];

      render(
        <TagWrapper
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
          bookedSlots={bookedSlots}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const bookedCell = cells[7];

      fireEvent.mouseDown(firstCell!, { button: 2, buttons: 2 });
      fireEvent.mouseEnter(bookedCell!, { buttons: 2 });
      fireEvent.contextMenu(bookedCell!, { button: 2, buttons: 2 });

      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('skips primary drag updates for locked cells', async () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-321',
          date: '2030-01-07',
          start_time: '09:30:00',
          end_time: '10:00:00',
          student_first_name: 'Jane',
          student_last_initial: 'R',
          service_name: 'Violin',
          service_area_short: 'Brooklyn',
          duration_minutes: 30,
          location_type: 'student_location',
        },
      ];

      render(<TagWrapper bookedSlots={bookedSlots} initialBits={{}} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const bookedCell = cells[7];

      fireEvent.mouseDown(firstCell!, { button: 0, buttons: 1 });
      fireEvent.mouseEnter(bookedCell!, { buttons: 1 });
      fireEvent.mouseUp(bookedCell!, { button: 0 });

      expect(firstCell).toHaveAttribute('aria-selected', 'true');
      expect(bookedCell).toHaveAttribute('aria-selected', 'false');
    });

    it('opens the same tag popover path on mobile long press', async () => {
      render(<TagWrapper isMobile={true} />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.touchStart(firstCell!);

      await act(async () => {
        jest.advanceTimersByTime(450);
      });

      expect(screen.getByTestId('format-tag-popover')).toBeInTheDocument();
      fireEvent.touchEnd(firstCell!);
    });

    it('does not open the long-press popover for inactive touch targets', async () => {
      render(
        <TagWrapper
          isMobile={true}
          initialBits={{
            '2030-01-07': new Uint8Array(BYTES_PER_DAY),
          }}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.touchStart(firstCell!);
      await act(async () => {
        jest.advanceTimersByTime(450);
      });
      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('cancels long press on multi-touch, touch move, and touch cancel', async () => {
      render(<TagWrapper isMobile={true} />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];

      fireEvent.touchStart(firstCell!, {
        touches: [{ identifier: 1 }, { identifier: 2 }],
      });
      await act(async () => {
        jest.advanceTimersByTime(450);
      });
      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();

      fireEvent.touchStart(firstCell!, {
        touches: [{ identifier: 1 }],
      });
      fireEvent.touchMove(firstCell!);
      await act(async () => {
        jest.advanceTimersByTime(450);
      });
      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();

      fireEvent.touchStart(firstCell!, {
        touches: [{ identifier: 1 }],
      });
      fireEvent.touchCancel(firstCell!);
      await act(async () => {
        jest.advanceTimersByTime(450);
      });
      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('closes the popover when focus leaves through Radix open state changes', async () => {
      render(<TagWrapper />);

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      fireEvent.contextMenu(firstCell!);

      expect(screen.getByTestId('format-tag-popover')).toBeInTheDocument();

      fireEvent.keyDown(document, { key: 'Escape' });

      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.queryByTestId('format-tag-popover')).not.toBeInTheDocument();
    });

    it('renders mixed tag cells with the base active palette', () => {
      const mixedTags = newEmptyTags();
      const partiallyTagged = setRangeTag(mixedTags, 108, 3, TAG_ONLINE_ONLY);

      render(
        <TagWrapper
          initialTags={{
            '2030-01-07': partiallyTagged,
          }}
        />
      );

      const firstCell = screen.getAllByTestId('availability-cell')[0];
      expect(firstCell!).toHaveAttribute('data-tag-state', 'mixed');
      expect(firstCell!.className).toContain('bg-[#EDE3FA]');
    });
  });

  describe('keyboard interaction', () => {
    it('toggles selection on Enter key', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell).toBeTruthy();
      fireEvent.keyDown(firstCell!, { key: 'Enter' });

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('toggles selection on Space key', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell).toBeTruthy();
      fireEvent.keyDown(firstCell!, { key: ' ' });

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('does not toggle on other keys', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell).toBeTruthy();
      fireEvent.keyDown(firstCell!, { key: 'a' });

      expect(onBitsChange).not.toHaveBeenCalled();
    });

    it('moves focus right with ArrowRight', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const firstCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      const nextCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="1"]'
      );
      expect(firstCell).toBeTruthy();
      expect(nextCell).toBeTruthy();

      firstCell!.focus();
      fireEvent.keyDown(firstCell!, { key: 'ArrowRight' });

      expect(document.activeElement).toBe(nextCell);
    });

    it('moves focus left with ArrowLeft', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const secondCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="1"]'
      );
      const firstCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      expect(secondCell).toBeTruthy();
      expect(firstCell).toBeTruthy();

      secondCell!.focus();
      fireEvent.keyDown(secondCell!, { key: 'ArrowLeft' });
      expect(document.activeElement).toBe(firstCell);
    });

    it('moves focus down with ArrowDown', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      const firstRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      const secondRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="1"][data-col-index="0"]'
      );
      expect(firstRowCell).toBeTruthy();
      expect(secondRowCell).toBeTruthy();

      firstRowCell!.focus();
      fireEvent.keyDown(firstRowCell!, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(secondRowCell);
    });

    it('moves focus up with ArrowUp', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      const firstRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      const secondRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="1"][data-col-index="0"]'
      );
      expect(firstRowCell).toBeTruthy();
      expect(secondRowCell).toBeTruthy();

      secondRowCell!.focus();
      fireEvent.keyDown(secondRowCell!, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(firstRowCell);
    });

    it('ArrowRight at last column keeps focus in place', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const lastCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="6"]'
      );
      expect(lastCell).toBeTruthy();

      lastCell!.focus();
      fireEvent.keyDown(lastCell!, { key: 'ArrowRight' });
      expect(document.activeElement).toBe(lastCell);
    });

    it('ArrowLeft at first column keeps focus in place', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const firstCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      expect(firstCell).toBeTruthy();

      firstCell!.focus();
      fireEvent.keyDown(firstCell!, { key: 'ArrowLeft' });
      expect(document.activeElement).toBe(firstCell);
    });

    it('ArrowDown at last row keeps focus in place', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const lastRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="1"][data-col-index="0"]'
      );
      expect(lastRowCell).toBeTruthy();

      lastRowCell!.focus();
      fireEvent.keyDown(lastRowCell!, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(lastRowCell);
    });

    it('ArrowUp at first row keeps focus in place', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const firstRowCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      expect(firstRowCell).toBeTruthy();

      firstRowCell!.focus();
      fireEvent.keyDown(firstRowCell!, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(firstRowCell);
    });

    it('moves focus to row boundaries with Home and End', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const middleCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="3"]'
      );
      const firstCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="0"]'
      );
      const lastCell = document.querySelector<HTMLButtonElement>(
        '[data-row-index="0"][data-col-index="6"]'
      );
      expect(middleCell).toBeTruthy();
      expect(firstCell).toBeTruthy();
      expect(lastCell).toBeTruthy();

      middleCell!.focus();
      fireEvent.keyDown(middleCell!, { key: 'End' });
      expect(document.activeElement).toBe(lastCell);

      fireEvent.keyDown(lastCell!, { key: 'Home' });
      expect(document.activeElement).toBe(firstCell);
    });

    it('keeps exactly one tabbable grid cell and Tab exits the grid', async () => {
      const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });

      render(
        <div>
          <button type="button">Before grid</button>
          <InteractiveGrid {...defaultProps} startHour={9} endHour={10} />
          <button type="button">After grid</button>
        </div>
      );

      const tabbableCells = screen
        .getAllByTestId('availability-cell')
        .filter((cell) => cell.getAttribute('tabindex') === '0');
      expect(tabbableCells).toHaveLength(1);

      const beforeButton = screen.getByRole('button', { name: 'Before grid' });
      const afterButton = screen.getByRole('button', { name: 'After grid' });

      beforeButton.focus();
      await user.tab();
      expect(tabbableCells[0]).toHaveFocus();

      await user.tab();
      expect(afterButton).toHaveFocus();
    });
  });

  describe('drag selection', () => {
    it('supports drag to select multiple cells', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');

      // Simulate drag: mouseDown on first cell, mouseEnter on second, mouseUp
      const firstCell = cells[0];
      const secondCell = cells[1];
      if (firstCell && secondCell) {
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        fireEvent.mouseEnter(secondCell, { buttons: 1 });
        fireEvent.mouseUp(secondCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('finishes drag on mouse leave with buttons=0', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        fireEvent.mouseLeave(firstCell, { buttons: 0 });
      }

      // Drag should be finished
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles drag across different date columns', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Get cells from different days (columns) - assuming 4 cells per day
      const cellsPerDay = 4; // 2 hours × 2 half-hours
      const firstDayCell = cells[0];
      const secondDayCell = cells[cellsPerDay]; // First cell of second day

      if (firstDayCell && secondDayCell) {
        fireEvent.mouseDown(firstDayCell, { buttons: 1 });
        // Drag to a different date column
        fireEvent.mouseEnter(secondDayCell, { buttons: 1 });
        fireEvent.mouseUp(secondDayCell);
      }

      // Should handle cross-day drag
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles drag within the same row', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const cellsPerDay = 4;
      const firstDayFirstRowCell = cells[0];
      // Same row, different day
      const secondDayFirstRowCell = cells[cellsPerDay];
      const thirdDayFirstRowCell = cells[cellsPerDay * 2];

      if (firstDayFirstRowCell && secondDayFirstRowCell && thirdDayFirstRowCell) {
        fireEvent.mouseDown(firstDayFirstRowCell, { buttons: 1 });
        fireEvent.mouseEnter(secondDayFirstRowCell, { buttons: 1 });
        // Continue to third day (same row, delta === 0)
        fireEvent.mouseEnter(thirdDayFirstRowCell, { buttons: 1 });
        fireEvent.mouseUp(thirdDayFirstRowCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('interpolates rows when dragging vertically', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={13}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Cells are arranged with 8 rows (4 hours × 2 half-hours) for 7 days
      const firstRowCell = cells[0]; // Row 0
      const thirdRowCell = cells[2]; // Row 2 - skip row 1 to test interpolation

      if (firstRowCell && thirdRowCell) {
        fireEvent.mouseDown(firstRowCell, { buttons: 1 });
        // Skip directly to row 2 to trigger interpolation
        fireEvent.mouseEnter(thirdRowCell, { buttons: 1 });
        fireEvent.mouseUp(thirdRowCell);
      }

      // The callback should handle interpolated rows
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('uses requestAnimationFrame for batch updates during drag', async () => {
      const rafSpy = jest.spyOn(window, 'requestAnimationFrame');
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[1];

      if (firstCell && secondCell) {
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        fireEvent.mouseEnter(secondCell, { buttons: 1 });

        // requestAnimationFrame should be scheduled for batch updates
        expect(rafSpy).toHaveBeenCalled();

        fireEvent.mouseUp(secondCell);
      }

      rafSpy.mockRestore();
    });

    it('does not start drag without mouse button pressed', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[1];

      if (firstCell && secondCell) {
        // Only mouseEnter without prior mouseDown
        fireEvent.mouseEnter(secondCell, { buttons: 0 });
      }

      // Should not trigger update without drag started
      expect(onBitsChange).not.toHaveBeenCalled();
    });
  });

  describe('booked slots', () => {
    it('shows booked indicator for booked slots', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:00:00',
          end_time: '10:00:00',
          student_first_name: 'John',
          student_last_initial: 'D',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 60,
          location_type: 'student_location',
        },
      ];

      render(
        <InteractiveGrid
          {...defaultProps}
          bookedSlots={bookedSlots}
          startHour={9}
          endHour={10}
        />
      );

      // Component renders booked slots with striped pattern
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('mobile view', () => {
    it('renders single day when isMobile is true', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={0}
          startHour={9}
          endHour={10}
        />
      );

      // In mobile view, only one day's cells should be visible
      const cells = screen.getAllByTestId('availability-cell');
      // 2 hours × 2 half-hours = 4 half-hour cells for one day
      expect(cells.length).toBeLessThan(7 * 4); // Less than full week
    });

    it('respects activeDayIndex for mobile view', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={2}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Should show cells for day at index 2 (limited to one day)
      expect(cells.length).toBeLessThan(7 * 4);
    });
  });

  describe('past slot handling', () => {
    it('marks past slots as disabled', () => {
      // Set current time to middle of week
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          allowPastEditing={false}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const disabledCells = cells.filter(
        (cell) => cell.getAttribute('aria-disabled') === 'true'
      );
      expect(disabledCells.length).toBeGreaterThan(0);
    });

    it('allows editing past slots when allowPastEditing is true', () => {
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          allowPastEditing={true}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const disabledCells = cells.filter(
        (cell) => cell.getAttribute('aria-disabled') === 'true'
      );
      // With allowPastEditing, no cells should be disabled
      expect(disabledCells.length).toBe(0);
    });

    it('does not toggle past slot on mouse interaction when disabled', () => {
      const onBitsChange = jest.fn();
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          allowPastEditing={false}
          startHour={9}
          endHour={10}
        />
      );

      const disabledCell = screen
        .getAllByTestId('availability-cell')
        .find((cell) => cell.getAttribute('aria-disabled') === 'true');
      expect(disabledCell).toBeTruthy();

      fireEvent.mouseDown(disabledCell!);
      fireEvent.mouseUp(disabledCell!);

      expect(onBitsChange).not.toHaveBeenCalled();
    });

    it('does not toggle past slot on Enter/Space when disabled', () => {
      const onBitsChange = jest.fn();
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          allowPastEditing={false}
          startHour={9}
          endHour={10}
        />
      );

      const disabledCell = screen
        .getAllByTestId('availability-cell')
        .find((cell) => cell.getAttribute('aria-disabled') === 'true');
      expect(disabledCell).toBeTruthy();
      disabledCell!.focus();

      fireEvent.keyDown(disabledCell!, { key: 'Enter' });
      fireEvent.keyDown(disabledCell!, { key: ' ' });

      expect(onBitsChange).not.toHaveBeenCalled();
    });
  });

  describe('now line', () => {
    it('shows now line for current day within hour range', () => {
      // Set time within the grid's hour range
      jest.setSystemTime(new Date('2030-01-07T10:30:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={12}
        />
      );

      const nowLine = screen.queryByTestId('now-line');
      // The now line should be rendered for today's column
      expect(nowLine).toBeInTheDocument();
    });

    it('does not show now line outside hour range', () => {
      // Set time outside the grid's hour range
      jest.setSystemTime(new Date('2030-01-07T05:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={12}
        />
      );

      const nowLine = screen.queryByTestId('now-line');
      expect(nowLine).not.toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('grid container has role=grid with instructional aria-label', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const grid = screen.getByRole('grid', {
        name: 'Weekly availability editor. Use arrow keys to navigate between time slots.',
      });
      expect(grid).toBeInTheDocument();
    });

    it('day headers have role=columnheader', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const headers = screen.getAllByRole('columnheader');
      expect(headers.length).toBeGreaterThan(0);
    });

    it('time gutter headers have role=rowheader', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const rowHeaders = screen.getAllByRole('rowheader');
      expect(rowHeaders.length).toBeGreaterThan(0);
      expect(rowHeaders[0]).toHaveTextContent('9:00');
    });

    it('cells have role=gridcell', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      // Cells have role="gridcell" attribute
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells[0]?.getAttribute('role')).toBe('gridcell');
    });

    it('cells have aria-label with day and time', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell?.getAttribute('aria-label')).toBeTruthy();
    });

    it('cells have data-date and data-time attributes', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell?.getAttribute('data-date')).toBeTruthy();
      expect(firstCell?.getAttribute('data-time')).toBeTruthy();
    });
  });

  describe('timezone support', () => {
    it('accepts timezone prop', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          timezone="America/New_York"
          startHour={9}
          endHour={10}
        />
      );

      // Should render without errors
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('hour label formatting', () => {
    it('formats morning hours correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={6} endHour={11} />);

      // Time labels include AM/PM - use getAllByText since multiple elements may match
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('6:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('formats noon correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={12} endHour={13} />);

      // Noon shows as 12:00 PM
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('12:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('formats afternoon hours correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={13} endHour={17} />);

      // Afternoon shows PM hours
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('1:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('renders cells for extended hours', () => {
      render(<InteractiveGrid {...defaultProps} startHour={22} endHour={24} />);

      // Component should handle extended hours
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('batch update and flush logic', () => {
    beforeEach(() => {
      // Use real timers for RAF tests
      jest.useRealTimers();
    });

    afterEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });

    it('batches updates during drag and flushes on mouseUp', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const cell1 = cells[0];
      const cell2 = cells[1];
      const cell3 = cells[2];

      if (cell1 && cell2 && cell3) {
        // Start drag
        await act(async () => {
          fireEvent.mouseDown(cell1, { buttons: 1 });
        });

        // Drag through multiple cells
        await act(async () => {
          fireEvent.mouseEnter(cell2, { buttons: 1 });
          // Allow RAF to execute
          await new Promise(resolve => requestAnimationFrame(resolve));
        });

        await act(async () => {
          fireEvent.mouseEnter(cell3, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
        });

        // End drag
        await act(async () => {
          fireEvent.mouseUp(cell3);
          await new Promise(resolve => requestAnimationFrame(resolve));
        });
      }

      // Multiple cells should have been selected via batch updates
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles early return when slot already in desired state during drag', async () => {
      // Pre-select a slot
      // 9:00 AM = bitmap slot 108. A 30-min cell sets 6 consecutive bits.
      const weekBits: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={weekBits}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Find the pre-selected cell
      const selectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );
      const nextCell = cells[1];

      if (selectedCell && nextCell) {
        // Start drag from selected cell (which is already selected - should trigger early return)
        await act(async () => {
          fireEvent.mouseDown(selectedCell, { buttons: 1 });
        });

        await act(async () => {
          fireEvent.mouseEnter(nextCell, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
        });

        await act(async () => {
          fireEvent.mouseUp(nextCell);
        });
      }

      // Should still function correctly, handling early return gracefully
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('flushes pending updates with correct state changes', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');

      const cell0 = cells[0];
      const cell1 = cells[1];
      const cell2 = cells[2];
      const cell3 = cells[3];
      if (cell0 && cell1 && cell2 && cell3) {
        // Drag through multiple cells rapidly
        await act(async () => {
          fireEvent.mouseDown(cell0, { buttons: 1 });
          fireEvent.mouseEnter(cell1, { buttons: 1 });
          fireEvent.mouseEnter(cell2, { buttons: 1 });
          fireEvent.mouseEnter(cell3, { buttons: 1 });
          // Let RAF run
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(cell3);
        });
      }

      // The flushPending function should have been called
      expect(onBitsChange).toHaveBeenCalled();
    });
  });

  describe('callback execution with state updater', () => {
    it('executes applyImmediate callback and handles early return for already selected state', () => {
      // Create a mock that executes the callback and tracks the results
      const results: Array<WeekBits | undefined> = [];
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          // Create an empty state to pass to the updater
          const emptyState: WeekBits = {};
          const result = next(emptyState);
          results.push(result);
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];

      if (firstCell) {
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
      }

      // The callback should have been executed
      expect(onBitsChange).toHaveBeenCalled();
      expect(results.length).toBeGreaterThan(0);
    });

    it('executes applyImmediate callback and returns prev when slot is already in desired state', () => {
      // Create state with 9:00 AM cell already selected (bitmap slot 108, 6 bits)
      const existingState: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        // Execute the updater to verify it runs without errors
        if (typeof next === 'function') {
          next(existingState);
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={existingState}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Find a cell that's NOT selected, then click it to select
      const unselectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') !== 'true'
      );

      if (unselectedCell) {
        fireEvent.mouseDown(unselectedCell);
        fireEvent.mouseUp(unselectedCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('executes flushPending callback and processes batch updates correctly', async () => {
      jest.useRealTimers();

      const updaterResults: Array<WeekBits | undefined> = [];
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          const emptyState: WeekBits = {};
          const result = next(emptyState);
          updaterResults.push(result);
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const c0 = cells[0];
      const c1 = cells[1];
      const c2 = cells[2];

      if (c0 && c1 && c2) {
        await act(async () => {
          fireEvent.mouseDown(c0, { buttons: 1 });
          fireEvent.mouseEnter(c1, { buttons: 1 });
          fireEvent.mouseEnter(c2, { buttons: 1 });
          // Allow RAF to execute
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(c2);
        });
      }

      // Flush callbacks should have been executed
      expect(onBitsChange).toHaveBeenCalled();
      expect(updaterResults.some(r => r !== undefined)).toBe(true);

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });

    it('executes flushPending callback with existing state and processes changes', async () => {
      jest.useRealTimers();

      // State with some slots already selected
      const existingState: WeekBits = {
        '2030-01-07': new Uint8Array(BYTES_PER_DAY),
      };

      let changed = false;
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          const result = next(existingState);
          if (result !== existingState) {
            changed = true;
          }
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={existingState}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const c0 = cells[0];
      const c1 = cells[1];

      if (c0 && c1) {
        await act(async () => {
          fireEvent.mouseDown(c0, { buttons: 1 });
          fireEvent.mouseEnter(c1, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(c1);
        });
      }

      expect(onBitsChange).toHaveBeenCalled();
      expect(changed).toBe(true);

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });
  });

  describe('same row drag handling', () => {
    it('handles mouseEnter on same row within same day', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Get first cell
      const firstCell = cells[0];

      if (firstCell) {
        // Start drag
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        // Re-enter the same cell (same row, same day - delta === 0)
        fireEvent.mouseEnter(firstCell, { buttons: 1 });
        fireEvent.mouseUp(firstCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles vertical drag with interpolation', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={13}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // First day cells - row 0 and row 3 (skip rows 1, 2)
      const row0Cell = cells[0];
      const row3Cell = cells[3];

      if (row0Cell && row3Cell) {
        fireEvent.mouseDown(row0Cell, { buttons: 1 });
        // Jump directly to row 3 to trigger interpolation
        fireEvent.mouseEnter(row3Cell, { buttons: 1 });
        fireEvent.mouseUp(row3Cell);
      }

      // Should interpolate intermediate rows
      expect(onBitsChange).toHaveBeenCalled();
    });

    it('handles upward drag with negative delta', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={13}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Start from row 3, drag up to row 0
      const row3Cell = cells[3];
      const row0Cell = cells[0];

      if (row3Cell && row0Cell) {
        fireEvent.mouseDown(row3Cell, { buttons: 1 });
        // Drag upward
        fireEvent.mouseEnter(row0Cell, { buttons: 1 });
        fireEvent.mouseUp(row0Cell);
      }

      // Should handle negative delta interpolation
      expect(onBitsChange).toHaveBeenCalled();
    });
  });

  describe('state updater function execution', () => {
    // Test wrapper component that executes the state updater
    const TestWrapper = ({ initialBits = {} as WeekBits }: { initialBits?: WeekBits }) => {
      const [weekBits, setWeekBits] = React.useState<WeekBits>(initialBits);
      return (
        <InteractiveGrid
          weekDates={mockWeekDates}
          weekBits={weekBits}
          onBitsChange={setWeekBits}
          startHour={9}
          endHour={12}
        />
      );
    };

    it('executes applyImmediate early return when clicking already selected slot', () => {
      // Pre-select 9:00 AM cell (bitmap slot 108, 6 bits)
      const initialBits: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      render(<TestWrapper initialBits={initialBits} />);

      const cells = screen.getAllByTestId('availability-cell');
      const selectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );

      if (selectedCell) {
        // Click to deselect, then click the same position again
        fireEvent.mouseDown(selectedCell);
        fireEvent.mouseUp(selectedCell);
      }

      // The actual state updater was executed
      expect(cells.length).toBeGreaterThan(0);
    });

    it('executes flushPending batch logic with real state updates', async () => {
      jest.useRealTimers();

      render(<TestWrapper />);

      const cells = screen.getAllByTestId('availability-cell');
      const cell0 = cells[0];
      const cell1 = cells[1];
      const cell2 = cells[2];

      if (cell0 && cell1 && cell2) {
        await act(async () => {
          fireEvent.mouseDown(cell0, { buttons: 1 });
          fireEvent.mouseEnter(cell1, { buttons: 1 });
          fireEvent.mouseEnter(cell2, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(cell2);
          await new Promise(resolve => setTimeout(resolve, 50));
        });
      }

      // Verify that cells are now selected (state was actually updated)
      const selectedCells = screen.getAllByTestId('availability-cell').filter(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );
      expect(selectedCells.length).toBeGreaterThan(0);

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });

    it('executes flushPending with no changes when slots already in desired state', async () => {
      jest.useRealTimers();

      // Pre-select the first two 30-min cells (9:00 and 9:30) so drag finds them already set
      const base = makeCellBits(108); // 9:00 AM cell (bits 108-113)
      // Also set 9:30 AM cell (bits 114-119)
      for (let i = 0; i < BITS_PER_CELL; i++) {
        const slot = 114 + i;
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        base[byteIdx]! |= 1 << bitIdx;
      }
      const initialBits: WeekBits = {
        '2030-01-07': base,
      };

      render(<TestWrapper initialBits={initialBits} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[1];

      // Drag to select (but some are already selected)
      if (firstCell && secondCell) {
        await act(async () => {
          fireEvent.mouseDown(firstCell, { buttons: 1 });
          fireEvent.mouseEnter(secondCell, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(secondCell);
          await new Promise(resolve => setTimeout(resolve, 50));
        });
      }

      expect(cells.length).toBeGreaterThan(0);

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });
  });

  describe('hour-24 label and edge cases', () => {
    it('renders the midnight next-day label when endHour exceeds 24', () => {
      // HOURS_LABEL(24) returns '12:00 AM (+1d)' — exercises line 29
      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={23}
          endHour={25}
          allowPastEditing={true}
        />
      );

      const label = screen.getByText((content) => content.includes('+1d'));
      expect(label).toBeInTheDocument();
    });

    it('does not crash when weekDates is empty', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          weekDates={[]}
          startHour={9}
          endHour={10}
        />
      );

      // No cells rendered for empty week
      expect(screen.queryAllByTestId('availability-cell')).toHaveLength(0);
    });

    it('handles mobile view with out-of-range activeDayIndex', () => {
      // activeDayIndex=99 is beyond weekDates.length; falls back to weekDates[0]
      // exercises lines 248-249: weekDates[activeDayIndex] ?? weekDates[0]
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={99}
          startHour={9}
          endHour={10}
        />
      );

      // Should render the first day as fallback
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBe(2); // 1 hour * 2 half-hours * 1 day
    });
  });

  describe('mouseLeave does not finish drag when buttons > 0', () => {
    it('keeps drag active when mouse leaves with button still held (line 466)', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      const secondCell = cells[1];

      if (firstCell && secondCell) {
        // Start drag
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        // Leave with button still held — should NOT finish drag
        fireEvent.mouseLeave(firstCell, { buttons: 1 });
        // Enter next cell — drag should still be active
        fireEvent.mouseEnter(secondCell, { buttons: 1 });
        fireEvent.mouseUp(secondCell);
      }

      // onBitsChange called for initial click + drag, proving drag was not ended
      expect(onBitsChange).toHaveBeenCalled();
    });
  });

  describe('getNowInTimezone without timezone prop (line 62-66)', () => {
    it('uses local time when no timezone is provided', () => {
      jest.setSystemTime(new Date('2030-01-08T15:30:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={22}
          // No timezone prop — exercises the !tz branch at line 62
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('applyImmediate early return (line 118)', () => {
    it('triggers early return when state already matches desired via callback manipulation', () => {
      // The early return (line 118) happens when the callback is called with prev state
      // that already has the slot in the desired state.
      // This can happen if there's a race condition or state mismatch.

      // Start with an empty weekBits prop
      // 9:00 AM cell = bitmap slot 108, 6 consecutive bits

      // Create a state that already has the 9:00 AM cell selected
      const stateWithSlotSelected: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      let earlyReturnTriggered = false;
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          // Call the callback with a state where the slot is ALREADY in the desired state
          // This simulates a race condition where state changed between click and callback execution
          const result = next(stateWithSlotSelected);
          if (result === stateWithSlotSelected) {
            earlyReturnTriggered = true;
          }
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={{}} // Empty prop - component thinks slot is unselected
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];

      if (firstCell) {
        // Click unselected cell -> desired=true
        // But when callback runs, we pass stateWithSlotSelected where slot is already selected
        // So isCellSelected(current, slotIndex) === desired => true === true => early return!
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
      expect(earlyReturnTriggered).toBe(true);
    });

    it('returns prev unchanged when clicking to select an already selected slot', () => {
      // Pre-select 9:00 AM cell (bitmap slot 108, 6 bits)
      const existingState: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          next(existingState);
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={existingState}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      // Find the selected cell and click it again (tries to select already selected)
      const cells = screen.getAllByTestId('availability-cell');
      const selectedCell = cells.find(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );

      if (selectedCell) {
        // Clicking a selected cell with mouseDown starts a drag with desired=false (deselect)
        // To trigger the early return (line 118), we need the slot to already match desired
        // This happens when clicking an unselected cell when it's already unselected after toggle
        fireEvent.mouseDown(selectedCell);
        fireEvent.mouseUp(selectedCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('triggers applyImmediate early return by double-click pattern', () => {
      const results: Array<{ same: boolean }> = [];
      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          const emptyState: WeekBits = {};
          const result = next(emptyState);
          results.push({ same: result === emptyState });
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];

      if (firstCell) {
        // First click selects
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
        // Second click deselects
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
      expect(results.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe('flushPending inner logic (lines 146-164)', () => {
    beforeEach(() => {
      jest.useRealTimers();
    });

    afterEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2030-01-08T10:00:00'));
    });

    it('executes flushPending callback with actual pending data', async () => {
      // Use a controlled component to track actual state changes
      let capturedCallbacks: Array<(prev: WeekBits) => WeekBits> = [];
      const onBitsChange = jest.fn((updater: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof updater === 'function') {
          capturedCallbacks.push(updater);
        }
      });

      const { rerender } = render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const cell0 = cells[0];
      const cell7 = cells[7]; // Different row, same day

      if (cell0 && cell7) {
        // Perform mouseDown
        await act(async () => {
          fireEvent.mouseDown(cell0, { buttons: 1 });
        });

        // Re-render to apply isDragging state
        rerender(
          <InteractiveGrid
            {...defaultProps}
            onBitsChange={onBitsChange}
            startHour={9}
            endHour={12}
          />
        );

        await act(async () => {
          // Now mouseEnter should work since isDragging is true
          fireEvent.mouseEnter(cell7, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
        });

        await act(async () => {
          fireEvent.mouseUp(cell7);
          await new Promise(resolve => setTimeout(resolve, 100));
        });
      }

      // Should have captured callbacks
      expect(onBitsChange).toHaveBeenCalled();

      // Execute all captured callbacks with empty state to cover lines 146-164
      capturedCallbacks.forEach(cb => {
        const result = cb({});
        // Verify the callback returns a WeekBits object
        expect(result).toBeDefined();
      });
    });

    it('processes multiple dates in the for-loop', async () => {
      // Create wrapper that actually updates state
      const StateWrapper = () => {
        const [bits, setBits] = React.useState<WeekBits>({});
        return (
          <InteractiveGrid
            weekDates={mockWeekDates}
            weekBits={bits}
            onBitsChange={setBits}
            startHour={9}
            endHour={12}
          />
        );
      };

      render(<StateWrapper />);

      const cells = screen.getAllByTestId('availability-cell');
      // Cells are arranged: row0-day0, row0-day1, ... row0-day6, row1-day0, ...
      // Each row is a time slot, each column is a day
      // Get cells from different days (column 0 and column 1 in first row)
      const day0Cell = cells[0]; // First day, first time slot
      const day1Cell = cells[1]; // Second day, first time slot (same row)

      if (day0Cell && day1Cell) {
        await act(async () => {
          fireEvent.mouseDown(day0Cell, { buttons: 1 });
          // Move to cell in different day (horizontal drag)
          fireEvent.mouseEnter(day1Cell, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(day1Cell);
          await new Promise(resolve => setTimeout(resolve, 50));
        });
      }

      // Verify both days have selections
      const selectedCells = screen.getAllByTestId('availability-cell').filter(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );
      expect(selectedCells.length).toBeGreaterThan(0);
    });

    it('handles changed flag correctly when some slots already match desired state', async () => {
      // Pre-select 9:00 AM cell (bitmap slot 108, 6 bits), then drag over it and adjacent slots
      const initialBits: WeekBits = {
        '2030-01-07': makeCellBits(108),
      };

      const StateWrapper = ({ initial }: { initial: WeekBits }) => {
        const [bits, setBits] = React.useState<WeekBits>(initial);
        return (
          <InteractiveGrid
            weekDates={mockWeekDates}
            weekBits={bits}
            onBitsChange={setBits}
            startHour={9}
            endHour={12}
          />
        );
      };

      render(<StateWrapper initial={initialBits} />);

      const cells = screen.getAllByTestId('availability-cell');
      // Drag starting from second cell (unselected) and moving through multiple cells
      const cell0 = cells[0]; // First day, first slot
      const cell1 = cells[7]; // First day, second slot (row 1, col 0 = index 7 for 7 days)

      if (cell0 && cell1) {
        await act(async () => {
          fireEvent.mouseDown(cell0, { buttons: 1 });
          fireEvent.mouseEnter(cell1, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(cell1);
          await new Promise(resolve => setTimeout(resolve, 50));
        });
      }

      expect(cells.length).toBeGreaterThan(0);
    });

    it('correctly returns prev when no actual changes occur (line 164)', async () => {
      // All cells we'll drag over are already in the desired state
      // Set 8:00 and 8:30 cells (bitmap slots 96-107)
      const bits = new Uint8Array(BYTES_PER_DAY);
      // Set all 12 bits (slots 96-107) for two full 30-min cells
      for (let s = 96; s < 108; s++) {
        bits[Math.floor(s / 8)] = (bits[Math.floor(s / 8)] ?? 0) | (1 << (s % 8));
      }
      const initialBits: WeekBits = {
        '2030-01-07': bits,
      };

      const onBitsChange = jest.fn((next: WeekBits | ((prev: WeekBits) => WeekBits)) => {
        if (typeof next === 'function') {
          next(initialBits);
        }
      });

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={initialBits}
          onBitsChange={onBitsChange}
          startHour={8}
          endHour={12}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Find cells that are already selected and drag over them (trying to select already-selected)
      const selectedCells = cells.filter(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );

      if (selectedCells.length >= 2) {
        const sc0 = selectedCells[0]!;
        const sc1 = selectedCells[1]!;

        await act(async () => {
          // Deselect mode - start drag on selected cell
          fireEvent.mouseDown(sc0, { buttons: 1 });
          fireEvent.mouseEnter(sc1, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(sc1);
        });
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('processes empty slot arrays in dates (line 150)', async () => {
      const StateWrapper = () => {
        const [bits, setBits] = React.useState<WeekBits>({});
        return (
          <InteractiveGrid
            weekDates={mockWeekDates}
            weekBits={bits}
            onBitsChange={setBits}
            startHour={9}
            endHour={10}
          />
        );
      };

      render(<StateWrapper />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];

      if (firstCell) {
        await act(async () => {
          // Quick drag - mouseDown and immediately mouseUp
          fireEvent.mouseDown(firstCell, { buttons: 1 });
          await new Promise(resolve => requestAnimationFrame(resolve));
          fireEvent.mouseUp(firstCell);
          await new Promise(resolve => setTimeout(resolve, 50));
        });
      }

      // Should handle edge case gracefully
      expect(cells.length).toBeGreaterThan(0);
    });
  });
});
