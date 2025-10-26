'use client';

import ProfileDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedProfile() {
  return (
    <EmbeddedContext.Provider value={true}>
      <ProfileDefault />
    </EmbeddedContext.Provider>
  );
}
