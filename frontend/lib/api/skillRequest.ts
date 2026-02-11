import { logger } from '@/lib/logger';

const SKILL_REQUEST_WEBHOOK_URL = 'https://instainstru.app.n8n.cloud/webhook/skill-request';

interface SkillRequestPayload {
  skill_name: string;
  instructor_id: string | null;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  is_founding_instructor: boolean;
  is_live: boolean;
  source: 'onboarding_skill_selection' | 'profile_skills_inline';
}

export async function submitSkillRequest(payload: SkillRequestPayload): Promise<void> {
  const response = await fetch(SKILL_REQUEST_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, submitted_at: new Date().toISOString() }),
  });

  if (!response.ok) {
    logger.error('Skill request webhook failed', new Error(`Webhook responded with ${response.status}`));
    throw new Error(`Webhook responded with ${response.status}`);
  }
}
