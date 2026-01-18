import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ValidationPreviewModal from '../ValidationPreviewModal';
import type { WeekValidationResponse } from '@/types/availability';
import { logger } from '@/lib/logger';

jest.mock('@/components/Modal', () => ({
  __esModule: true,
  default: ({ isOpen, title, children }: { isOpen: boolean; title?: string; children?: React.ReactNode }) =>
    isOpen ? (
      <div>
        {title && <div>{title}</div>}
        {children}
      </div>
    ) : null,
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn() },
}));

const baseResults: WeekValidationResponse = {
  valid: true,
  summary: {
    total_operations: 3,
    valid_operations: 2,
    invalid_operations: 1,
    estimated_changes: { slots_added: 2, slots_removed: 1 },
    operations_by_type: { add: 1, remove: 1, update: 1 },
    has_conflicts: true,
  },
  details: [
    {
      operation_index: 0,
      action: 'add',
      date: '2025-01-01',
      start_time: '10:00',
      end_time: '11:00',
      reason: 'Valid',
    },
    {
      operation_index: 1,
      action: 'remove',
      date: '2025-01-02',
      start_time: '12:00',
      end_time: '13:00',
      reason: 'Valid',
    },
    {
      operation_index: 2,
      action: 'update',
      date: '2025-01-03',
      start_time: '14:00',
      end_time: '15:00',
      reason: 'Conflicts with booking',
      conflicts_with: [{ start_time: '14:30', end_time: '15:30' }],
    },
  ],
  warnings: ['Overlapping slot'],
};

describe('ValidationPreviewModal', () => {
  const onClose = jest.fn();
  const onConfirm = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns null when closed', () => {
    const { container } = render(
      <ValidationPreviewModal
        isOpen={false}
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('returns null when there are no validation results', () => {
    const { container } = render(
      <ValidationPreviewModal
        isOpen
        validationResults={null}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders summary and warnings', () => {
    render(
      <ValidationPreviewModal
        isOpen
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText(/Summary/i)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/Warnings:/i)).toBeInTheDocument();
    expect(screen.getByText('Overlapping slot')).toBeInTheDocument();
  });

  it('renders conflicts with conflict details', () => {
    render(
      <ValidationPreviewModal
        isOpen
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByRole('heading', { name: /conflicts/i })).toBeInTheDocument();
    expect(screen.getByText(/Conflicts with booking\(s\): 14:30 - 15:30/i)).toBeInTheDocument();
    expect(screen.getByText(/↻ Update/i)).toBeInTheDocument();
  });

  it('renders valid operations list with formatted actions', () => {
    render(
      <ValidationPreviewModal
        isOpen
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText(/\+ Add/i)).toBeInTheDocument();
    expect(screen.getByText(/- Remove/i)).toBeInTheDocument();
  });

  it('logs and confirms when valid', async () => {
    const user = userEvent.setup();
    render(
      <ValidationPreviewModal
        isOpen
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    await user.click(screen.getByRole('button', { name: /confirm save/i }));
    expect(logger.info).toHaveBeenCalledWith('Validation preview confirmed', {
      totalOperations: 3,
      conflicts: 1,
    });
    expect(onConfirm).toHaveBeenCalled();
  });

  it('disables actions and shows saving state', () => {
    render(
      <ValidationPreviewModal
        isOpen
        validationResults={baseResults}
        onClose={onClose}
        onConfirm={onConfirm}
        isSaving
      />
    );

    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled();
    expect(screen.getByText(/saving/i)).toBeInTheDocument();
  });
});
