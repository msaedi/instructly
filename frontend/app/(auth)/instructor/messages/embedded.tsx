'use client';

import MessagesDefault from './page';
import { EmbeddedContext } from '../_embedded/EmbeddedContext';

export default function EmbeddedMessages() {
  return (
    <EmbeddedContext.Provider value={true}>
      <MessagesDefault />
    </EmbeddedContext.Provider>
  );
}
