import { maskPhoneDisplay } from '@/lib/phoneVerification';
import type { PhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';

type PhoneVerificationFieldProps = {
  flow: PhoneVerificationFlow;
  label: string;
  inputId: string;
  codeInputId: string;
  className?: string;
};

export function PhoneVerificationField({
  flow,
  label,
  inputId,
  codeInputId,
  className,
}: PhoneVerificationFieldProps) {
  return (
    <div className={className}>
      <label
        htmlFor={inputId}
        className="block text-xs text-gray-600 dark:text-gray-400"
      >
        {label}
      </label>
      <div className="mt-1">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
          <input
            id={inputId}
            type="tel"
            inputMode="tel"
            value={flow.phoneInput}
            onChange={(event) => flow.handlePhoneInputChange(event.target.value)}
            disabled={flow.showPendingPhoneState}
            placeholder="(212) 555-1001"
            className={`w-full px-3 py-2 insta-form-input focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/40 ${
              flow.showPendingPhoneState
                ? 'insta-form-input-readonly cursor-not-allowed pointer-events-none select-none'
                : ''
            }`}
          />
          {flow.showVerifiedPhoneState ? (
            <span className="inline-flex h-10 shrink-0 items-center rounded-md bg-green-50 px-3 text-sm font-semibold text-green-700 dark:bg-green-900/30 dark:text-green-300">
              Verified
            </span>
          ) : null}
          {flow.showPendingPhoneState ? (
            <span className="inline-flex h-10 shrink-0 items-center rounded-md bg-amber-50 px-3 text-sm font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
              Pending
            </span>
          ) : null}
          {!flow.showVerifiedPhoneState && !flow.showPendingPhoneState && flow.showVerifyPhoneAction ? (
            <button
              type="button"
              onClick={() => void flow.sendCode()}
              disabled={flow.updatePhonePending || flow.sendVerificationPending}
              className="insta-primary-btn inline-flex h-10 shrink-0 items-center justify-center rounded-md px-4 text-sm font-semibold text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {flow.updatePhonePending || flow.sendVerificationPending ? 'Sending…' : 'Verify'}
            </button>
          ) : null}
        </div>

        {!flow.showVerifiedPhoneState && !flow.showPendingPhoneState && flow.showVerifyPhoneAction ? (
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            We&apos;ll send a 6-digit verification code to this number.
          </p>
        ) : null}

        {flow.showPendingPhoneState ? (
          <div className="mt-3 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/40">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Code sent to {maskPhoneDisplay(flow.phoneInput || flow.phoneNumber || '')}
            </p>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                id={codeInputId}
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={flow.phoneCode}
                onChange={(event) => {
                  flow.setPhoneCode(event.target.value.replace(/\D/g, ''));
                }}
                placeholder="123456"
                className="w-full px-3 py-2 insta-form-input text-center tracking-[0.35em] focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/40 sm:max-w-[220px]"
              />
              <button
                type="button"
                onClick={() => void flow.confirmCode()}
                disabled={flow.confirmVerificationPending}
                className="insta-primary-btn inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold text-white transition focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {flow.confirmVerificationPending ? 'Submitting…' : 'Submit'}
              </button>
              <button
                type="button"
                onClick={() => void flow.sendCode()}
                disabled={flow.sendVerificationPending || flow.resendCooldown > 0}
                className={`inline-flex h-10 items-center justify-center rounded-md border px-4 text-sm font-semibold transition-colors ${
                  flow.sendVerificationPending || flow.resendCooldown > 0
                    ? 'cursor-not-allowed border-gray-200 text-gray-400 dark:border-gray-700 dark:text-gray-500'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-100 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800'
                }`}
              >
                {flow.resendCooldown > 0
                  ? `Resend (${flow.resendCooldown}s)`
                  : flow.sendVerificationPending
                    ? 'Sending…'
                    : 'Resend'}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
