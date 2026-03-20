function normalizeHostname(hostname: string | null | undefined): string {
  if (!hostname) return '';
  const lower = hostname.toLowerCase().trim();
  const normalized = lower.startsWith('www.') ? lower.slice(4) : lower;
  const [host = ''] = normalized.split(':', 1);
  return host;
}

const BETA_HOSTS = new Set(['beta.instainstru.com', 'beta-local.instainstru.com']);

export function getPublicProfileLaunchState(
  studentLaunchEnabled?: boolean | null,
  hostname?: string | null,
): {
  isEnabled: boolean;
  title: string;
} {
  const currentHost = normalizeHostname(
    hostname ?? (typeof window !== 'undefined' ? window.location.hostname : null),
  );
  const isEnabled = BETA_HOSTS.has(currentHost) ? studentLaunchEnabled === true : true;
  return {
    isEnabled,
    title: isEnabled
      ? 'View your public instructor page'
      : 'Available after student launch',
  };
}
