'use client';

import ReferralsPage from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedReferrals() {
  return (
    <EmbeddedContext.Provider value={true}>
      <ReferralsPage />
    </EmbeddedContext.Provider>
  );
}
