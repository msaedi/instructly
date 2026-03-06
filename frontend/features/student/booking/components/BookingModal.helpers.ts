import type { Service } from '../types';

export type BookingFormErrors = Partial<{
  name: string;
  email: string;
  phone: string;
  agreedToTerms: string;
  service: string;
}>;

export type BookingFormData = {
  name: string;
  email: string;
  phone: string;
  notes: string;
  agreedToTerms: boolean;
};

export const removeBookingFieldError = (
  errors: BookingFormErrors,
  field: keyof BookingFormErrors,
): BookingFormErrors => {
  if (!errors[field]) return errors;
  const next = { ...errors };
  delete next[field];
  return next;
};

export const validateBookingForm = (
  bookingFormData: BookingFormData,
  service: Service | null,
): BookingFormErrors => {
  const nextErrors: BookingFormErrors = {};

  if (!bookingFormData.name.trim()) {
    nextErrors.name = 'Full name is required';
  }

  if (!bookingFormData.email.trim()) {
    nextErrors.email = 'Email is required';
  }

  if (!bookingFormData.phone.trim()) {
    nextErrors.phone = 'Phone number is required';
  }

  if (!bookingFormData.agreedToTerms) {
    nextErrors.agreedToTerms = 'Please agree to the terms and cancellation policy';
  }

  if (!service) {
    nextErrors.service = 'Please select a service';
  }

  return nextErrors;
};

export const requireBookingService = (
  service: Service | null,
): Service => {
  if (!service) {
    throw new Error('Booking submit requires a selected service');
  }
  return service;
};
