import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OnboardingProgressHeader } from '../OnboardingProgressHeader';
import { useOnboardingStepStatus } from '../useOnboardingStepStatus';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('../useOnboardingStepStatus', () => ({
  useOnboardingStepStatus: jest.fn(),
}));

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => (
    <div data-testid="user-profile-dropdown" />
  );
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return MockUserProfileDropdown;
});

const useOnboardingStepStatusMock = useOnboardingStepStatus as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const stepStatusDoneFailed = {
  'account-setup': 'done',
  'skill-selection': 'failed',
  'verify-identity': 'pending',
  'payment-setup': 'pending',
} as const;

describe('OnboardingProgressHeader', () => {
  const pushMock = jest.fn();
  let originalGetBoundingClientRect: () => DOMRect;

  beforeEach(() => {
    pushMock.mockReset();
    useRouterMock.mockReturnValue({ push: pushMock });
    useOnboardingStepStatusMock.mockReturnValue({ stepStatus: stepStatusDoneFailed });
    originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;
  });

  afterEach(() => {
    HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
  });

  it('renders statuses and uses bounce animation for the first step', async () => {
    render(
      <OnboardingProgressHeader activeStep="account-setup" stepStatus={stepStatusDoneFailed} />
    );

    expect(screen.getByTestId('onboarding-header')).toBeInTheDocument();
    const step1 = screen.getByTitle('Step 1: Account Setup');
    expect(step1.className).toContain('bg-[#7E22CE]');
    expect(step1.querySelector('.icon-check')).toBeInTheDocument();

    const art = screen.getByTestId('onboarding-header-art');
    expect(art.className).toContain('inst-anim-walk-profile');
  });

  it('uses auto-evaluated status when enabled', () => {
    useOnboardingStepStatusMock.mockReturnValue({
      stepStatus: {
        'account-setup': 'pending',
        'skill-selection': 'done',
        'verify-identity': 'pending',
        'payment-setup': 'pending',
      },
    });

    render(
      <OnboardingProgressHeader
        activeStep="skill-selection"
        autoEvaluate
        stepStatus={stepStatusDoneFailed}
      />
    );

    const step2 = screen.getByTitle('Step 2: Add Skills');
    expect(step2.className).toContain('bg-[#7E22CE]');
    expect(step2.querySelector('.icon-check')).toBeInTheDocument();
  });

  it('positions the walker using button geometry and responds to resize', async () => {
    HTMLElement.prototype.getBoundingClientRect = function () {
      if (this.id === 'progress-step-1') {
        return { left: 50, width: 20 } as DOMRect;
      }
      if (typeof this.className === 'string' && this.className.includes('min-[1400px]:flex')) {
        return { left: 10, width: 400 } as DOMRect;
      }
      return { left: 0, width: 0 } as DOMRect;
    };

    render(
      <OnboardingProgressHeader
        activeStep="skill-selection"
        stepStatus={stepStatusDoneFailed}
        completedSteps={{ 'account-setup': true }}
      />
    );

    const art = screen.getByTestId('onboarding-header-art');
    await waitFor(() => {
      expect(art.style.left).toBe('42px');
    });

    fireEvent(window, new Event('resize'));
    await waitFor(() => {
      expect(art.style.left).toBe('42px');
    });
  });

  it('navigates on non-active steps and respects allowClickAll for active step', () => {
    const { rerender } = render(
      <OnboardingProgressHeader
        activeStep="skill-selection"
        stepStatus={stepStatusDoneFailed}
      />
    );

    fireEvent.click(screen.getByTitle('Step 2: Add Skills'));
    expect(pushMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTitle('Step 1: Account Setup'));
    expect(pushMock).toHaveBeenCalledWith('/instructor/onboarding/account-setup');

    pushMock.mockReset();
    rerender(
      <OnboardingProgressHeader
        activeStep="skill-selection"
        stepStatus={stepStatusDoneFailed}
        allowClickAll
      />
    );

    fireEvent.click(screen.getByTitle('Step 2: Add Skills'));
    expect(pushMock).toHaveBeenCalledWith('/instructor/onboarding/skill-selection');
  });
});
