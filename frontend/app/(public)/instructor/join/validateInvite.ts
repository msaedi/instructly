import { httpGet } from '@/lib/http';
import type { InviteValidateResult } from '@/app/(public)/instructor/inviteTypes';

export async function validateInviteCode(
  code: string,
  emailParam?: string | null,
): Promise<{ data: InviteValidateResult; trimmed: string }> {
  const trimmed = code.trim().toUpperCase();
  const data = await httpGet<InviteValidateResult>('/api/beta/invites/validate', {
    query: {
      invite_code: trimmed,
      email: emailParam || undefined,
    },
  });
  return { data, trimmed };
}
