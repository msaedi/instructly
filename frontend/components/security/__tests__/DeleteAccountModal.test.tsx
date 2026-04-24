import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeleteAccountModal from '../DeleteAccountModal';

const renderModal = (props?: {
  email?: string;
  onClose?: jest.Mock;
  onConfirm?: jest.Mock;
  isSubmitting?: boolean;
}) => {
  const onClose = props?.onClose ?? jest.fn();
  const onConfirm = props?.onConfirm ?? jest.fn();
  render(
    <DeleteAccountModal
      email={props?.email ?? 'user@example.com'}
      onClose={onClose}
      onConfirm={onConfirm}
      {...(props?.isSubmitting !== undefined ? { isSubmitting: props.isSubmitting } : {})}
    />
  );
  return { onClose, onConfirm };
};

describe('DeleteAccountModal', () => {
  it('renders the required delete confirmation copy', () => {
    renderModal();

    expect(screen.getByRole('dialog', { name: 'Delete your account?' })).toBeInTheDocument();
    expect(screen.getByText(/permanently deletes your iNSTAiNSTRU instructor account/i)).toBeInTheDocument();
    expect(screen.getByText(/completed bookings and reviews will be retained/i)).toBeInTheDocument();
    expect(screen.getByText(/We'll email you a confirmation/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Type your email to confirm')).toHaveAttribute('autocomplete', 'new-password');
  });

  it('disables delete until the typed email matches case-insensitively', async () => {
    const user = userEvent.setup();
    renderModal({ email: 'User@Example.com' });

    const input = screen.getByLabelText('Type your email to confirm');
    const deleteButton = screen.getByRole('button', { name: 'Delete account' });

    expect(deleteButton).toBeDisabled();

    await user.type(input, 'wrong@example.com');
    expect(deleteButton).toBeDisabled();

    await user.clear(input);
    await user.type(input, '  user@example.com  ');
    expect(deleteButton).not.toBeDisabled();
  });

  it('handles cancel and confirm actions', async () => {
    const user = userEvent.setup();
    const { onClose, onConfirm } = renderModal();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    await user.type(screen.getByLabelText('Type your email to confirm'), 'user@example.com');
    await user.click(screen.getByRole('button', { name: 'Delete account' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not submit with Enter until the typed email matches', async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderModal();
    const input = screen.getByLabelText('Type your email to confirm');

    await user.type(input, 'wrong@example.com');
    await user.keyboard('{Enter}');

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Delete account' })).toBeDisabled();
  });

  it('guards direct form submits while the typed email does not match', () => {
    const { onConfirm } = renderModal();
    const input = screen.getByLabelText('Type your email to confirm');

    const form = input.closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('submits with Enter when the typed email matches', async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderModal();

    await user.type(screen.getByLabelText('Type your email to confirm'), 'user@example.com');
    await user.keyboard('{Enter}');

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('still closes with Escape after adding form submit semantics', async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal();

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('disables actions and shows loading state while submitting', () => {
    renderModal({ isSubmitting: true });

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deleting...' })).toBeDisabled();
  });
});
