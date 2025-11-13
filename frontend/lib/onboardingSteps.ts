export type StepKey = 'account-setup' | 'skill-selection' | 'verify-identity' | 'payment-setup';

export const STEP_KEYS: StepKey[] = ['account-setup', 'skill-selection', 'verify-identity', 'payment-setup'];

export type StepState = {
  visited: boolean;
  completed: boolean;
};

export type OnboardingStatusMap = Record<StepKey, StepState>;

export const createEmptyStatusMap = (): OnboardingStatusMap =>
  STEP_KEYS.reduce((acc, key) => {
    acc[key] = { visited: false, completed: false };
    return acc;
  }, {} as OnboardingStatusMap);
