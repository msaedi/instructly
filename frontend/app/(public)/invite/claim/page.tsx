import { redirect } from 'next/navigation';

const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

type SearchParams = { [key: string]: string | string[] | undefined };
type SearchParamsPromise = Promise<SearchParams> | undefined;

function buildJoinHref(token: string, searchParams: SearchParams): string {
  const params = new URLSearchParams();
  params.set('invite_code', token);
  UTM_KEYS.forEach((key) => {
    const value = searchParams[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      params.set(key, value.trim());
    }
  });
  return `/instructor/join?${params.toString()}`;
}

async function resolveSearchParams(input: SearchParamsPromise): Promise<SearchParams> {
  const resolved = await Promise.resolve(input ?? {});
  return resolved ?? {};
}

export default async function InviteClaimPage({ searchParams }: { searchParams?: Promise<SearchParams> }) {
  const resolvedSearchParams = await resolveSearchParams(searchParams);

  const tokenParam = resolvedSearchParams?.['token'];
  const token = typeof tokenParam === 'string' ? tokenParam.trim() : '';

  if (!token) {
    return (
      <div className="min-h-screen bg-[#F9F5FF] flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg rounded-3xl bg-white shadow-2xl p-8 space-y-6 text-center">
          <p className="text-sm font-semibold tracking-widest text-[#7E22CE] uppercase">
            iNSTAiNSTRU
          </p>
          <h1 className="text-2xl font-bold text-gray-900">Invite link invalid</h1>
          <p className="text-base text-gray-600">
            We couldn&apos;t find a valid token in this link. Double-check the email or request a new invite.
          </p>
          <p className="text-sm text-gray-500">
            Need help? Contact{' '}
            <a className="text-[#7E22CE] font-semibold underline" href="mailto:support@instainstru.com">
              support@instainstru.com
            </a>
            .
          </p>
        </div>
      </div>
    );
  }

  const joinHref = buildJoinHref(token, resolvedSearchParams);
  redirect(joinHref);
}
