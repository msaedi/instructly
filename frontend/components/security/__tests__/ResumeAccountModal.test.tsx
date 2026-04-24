import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ResumeAccountModal from '../ResumeAccountModal';

const renderModal = (props?: {
  onClose?: jest.Mock;
  onConfirm?: jest.Mock;
  isSubmitting?: boolean;
}) => {
  const onClose = props?.onClose ?? jest.fn();
  const onConfirm = props?.onConfirm ?? jest.fn();
  render(
    <ResumeAccountModal
      onClose={onClose}
      onConfirm={onConfirm}
      {...(props?.isSubmitting !== undefined ? { isSubmitting: props.isSubmitting } : {})}
    />
  );
  return { onClose, onConfirm };
};

describe('ResumeAccountModal', () => {
  it('renders the required resume confirmation copy', () => {
    renderModal();

    expect(screen.getByRole('dialog', { name: 'Resume your account?' })).toBeInTheDocument();
    expect(screen.getByText(/visible in search/i)).toBeInTheDocument();
    expect(screen.getByText(/We'll email you a confirmation/i)).toBeInTheDocument();
  });

  it('handles cancel and confirm actions', async () => {
    const user = userEvent.setup();
    const { onClose, onConfirm } = renderModal();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Resume account' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('disables actions and shows loading state while submitting', () => {
    renderModal({ isSubmitting: true });

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Resuming...' })).toBeDisabled();
  });
});
