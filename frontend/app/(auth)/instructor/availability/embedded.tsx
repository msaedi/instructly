'use client';

import AvailabilityDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedAvailability() {
  return (
    <EmbeddedContext.Provider value={true}>
      <AvailabilityDefault />
    </EmbeddedContext.Provider>
  );
}
