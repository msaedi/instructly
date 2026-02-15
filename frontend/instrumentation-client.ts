import * as Sentry from '@sentry/nextjs';
import { initBotId } from 'botid/client/core';

import { BOTID_PROTECT_RULES } from '@/lib/security/protected-mutation-routes';

// BotID challenge scripts are served by hosted infrastructure,
// not available on localhost — skip in development.
if (process.env.NODE_ENV === 'production') {
  initBotId({
    protect: BOTID_PROTECT_RULES,
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
