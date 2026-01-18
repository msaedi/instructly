import { render, screen } from '@testing-library/react';
import React from 'react';
import TimeSelectionFacade, { TimeSelectionFacadeProps } from '../TimeSelectionFacade';

const modalMock = jest.fn<React.ReactElement, [TimeSelectionFacadeProps]>(
  () => <div data-testid="time-selection-modal" />
);

jest.mock('../../components/TimeSelectionModal', () => ({
  __esModule: true,
  default: (props: TimeSelectionFacadeProps) => modalMock(props),
}));

describe('TimeSelectionFacade', () => {
  beforeEach(() => {
    modalMock.mockClear();
  });

  it('renders the time selection modal', () => {
    const props: TimeSelectionFacadeProps = {
      isOpen: true,
      onClose: jest.fn(),
      instructor: {
        user_id: 'user-1',
        user: { first_name: 'Alex', last_initial: 'Q' },
        services: [{ duration_options: [60], hourly_rate: 50, skill: 'Piano' }],
      },
    };
    render(<TimeSelectionFacade {...props} />);

    expect(screen.getByTestId('time-selection-modal')).toBeInTheDocument();
  });

  it('forwards props to the modal', () => {
    const onClose = jest.fn();
    const props: TimeSelectionFacadeProps = {
      isOpen: true,
      onClose,
      instructor: {
        user_id: 'user-2',
        user: { first_name: 'Sam', last_initial: 'K' },
        services: [{ duration_options: [45], hourly_rate: 65, skill: 'Guitar' }],
      },
    };
    render(<TimeSelectionFacade {...props} />);

    expect(modalMock).toHaveBeenCalledWith(
      expect.objectContaining({ isOpen: true, onClose })
    );
  });
});
