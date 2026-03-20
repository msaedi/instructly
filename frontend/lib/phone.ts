export function formatPhoneDisplay(phone: string): string {
  const digits = phone.replace(/\D/g, '').replace(/^1/, '');

  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }

  return phone;
}
