'use client';

import EarningsDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedEarnings() {
  return (
    <EmbeddedContext.Provider value={true}>
      <EarningsDefault />
    </EmbeddedContext.Provider>
  );
}
