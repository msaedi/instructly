import { formatPhoneDisplay } from '@/lib/phone';

export const E164_PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;

export function formatPhoneVerificationInput(value: string): string {
  let cleaned = value.replace(/\D/g, '');

  if (cleaned.length === 11 && cleaned[0] === '1') {
    cleaned = cleaned.slice(1);
  }

  if (cleaned.length <= 3) {
    return cleaned;
  }
  if (cleaned.length <= 6) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3)}`;
  }
  return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
}

export function formatPhoneForApi(phone: string): string {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `+1${cleaned}`;
  }
  if (cleaned.length === 11 && cleaned[0] === '1') {
    return `+${cleaned}`;
  }
  return phone.trim();
}

export function maskPhoneDisplay(phone: string): string {
  const display = formatPhoneDisplay(phone);
  const digits = display.replace(/\D/g, '');
  if (digits.length !== 10) {
    return display;
  }
  return `(XXX) XXX-${digits.slice(-4)}`;
}
