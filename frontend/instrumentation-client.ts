import * as Sentry from '@sentry/nextjs';
import { initBotId } from 'botid/client/core';

import { BOTID_PROTECT_RULES } from '@/lib/security/protected-mutation-routes';

// BotID challenge scripts are served by hosted infrastructure,
// not available on localhost — skip in development.
// Deferred to idle callback so it doesn't block hydration (TBT).
// Safe because the earliest mutation requires user interaction post-hydration.
if (process.env.NODE_ENV === 'production') {
  const init = () => initBotId({ protect: BOTID_PROTECT_RULES });
  if (typeof requestIdleCallback !== 'undefined') {
    requestIdleCallback(init);
  } else {
    setTimeout(init, 0);
  }
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
