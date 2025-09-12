// frontend/features/student/booking/index.ts

// Public, stable surface for external consumers
export { default as BookingModal } from './components/BookingModal';
export { default as TimeSelectionModal } from './components/TimeSelectionModal';
export * from './types';
export { useAuth } from './hooks/useAuth';
// Do not export useCreateBooking here to avoid cross-feature runtime coupling
