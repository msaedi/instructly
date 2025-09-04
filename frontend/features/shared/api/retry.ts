export async function backoff(fn: () => Promise<Response>, opts: { maxRetries?: number } = { maxRetries: 3 }) {
  let attempt = 0;
  let delay = 1000;
  const maxRetries = opts.maxRetries ?? 3;
  while (true) {
    const res = await fn();
    if (res.status !== 429) return res;
    const ra = Number(res.headers.get('Retry-After') ?? '0');
    const wait = Math.max(ra * 1000, delay);
    await new Promise((r) => setTimeout(r, wait));
    attempt++;
    delay *= 2;
    if (attempt > maxRetries) return res;
  }
}
