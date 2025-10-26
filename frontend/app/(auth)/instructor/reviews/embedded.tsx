'use client';

import ReviewsDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedReviews() {
  return (
    <EmbeddedContext.Provider value={true}>
      <ReviewsDefault />
    </EmbeddedContext.Provider>
  );
}
