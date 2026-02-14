import * as Sentry from '@sentry/nextjs';
import { initBotId } from 'botid/client/core';

import { BOTID_PROTECT_RULES } from '@/lib/security/protected-mutation-routes';

initBotId({
  protect: BOTID_PROTECT_RULES,
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
