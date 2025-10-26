'use client';

import BookingsDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedBookings() {
  return (
    <EmbeddedContext.Provider value={true}>
      <BookingsDefault />
    </EmbeddedContext.Provider>
  );
}
