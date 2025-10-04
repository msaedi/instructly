import { fireEvent, render, screen } from '@testing-library/react';
import { BackgroundCheckDisclosureModal } from '@/components/consent/BackgroundCheckDisclosureModal';
import { FTC_RIGHTS_URL } from '@/config/constants';

describe('BackgroundCheckDisclosureModal', () => {
  it('renders required content sections and FTC link', () => {
    render(
      <BackgroundCheckDisclosureModal
        isOpen
        onAccept={jest.fn()}
        onDecline={jest.fn()}
      />
    );

    expect(screen.getByText(/Information we may obtain/i)).toBeInTheDocument();
    expect(screen.getByText(/Consumer reporting agency contact details/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Summary of Your Rights Under the Fair Credit Reporting Act/i })).toHaveAttribute(
      'href',
      FTC_RIGHTS_URL
    );
  });

  it('disables accept button until the disclosure is scrolled to the end', () => {
    const handleAccept = jest.fn();

    render(
      <BackgroundCheckDisclosureModal
        isOpen
        onAccept={handleAccept}
        onDecline={jest.fn()}
      />
    );

    const acceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });
    expect(acceptButton).toBeDisabled();

    const scrollRegion = screen.getByLabelText('Background check disclosure content');
    Object.defineProperty(scrollRegion, 'scrollHeight', { value: 200, configurable: true });
    Object.defineProperty(scrollRegion, 'clientHeight', { value: 100, configurable: true });

    fireEvent.scroll(scrollRegion, {
      currentTarget: Object.assign(scrollRegion, { scrollTop: 110 }),
    });

    expect(acceptButton).not.toBeDisabled();
    fireEvent.click(acceptButton);
    expect(handleAccept).toHaveBeenCalledTimes(1);
  });
});
