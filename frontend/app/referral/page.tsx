import Link from 'next/link';

export default function ReferralLandingPage() {
  return (
    <main className="relative overflow-hidden bg-gradient-to-b from-white via-purple-50 to-white">
      <div className="mx-auto flex min-h-[70vh] w-full max-w-5xl flex-col gap-16 px-4 py-16 sm:px-6 lg:flex-row lg:items-center lg:gap-20 lg:px-8">
        <section className="max-w-xl">
          <p className="mb-4 inline-flex items-center rounded-full bg-[#7E22CE]/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-[#7E22CE]">
            Give $20 · Get $20
          </p>
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
            Book your first $75+ lesson and get $20 off.
          </h1>
          <p className="mt-6 text-base leading-7 text-gray-600">
            Join Theta with a friend&rsquo;s link and save {"$"}20 on your first lesson. Book within 30 days and you&rsquo;ll both earn credits for the next session.
          </p>

          <div className="mt-10 flex flex-col items-start gap-3 sm:flex-row">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center rounded-lg bg-[#7E22CE] px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
            >
              Create an account
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-lg border border-gray-200 bg-white px-6 py-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
            >
              Open the app
            </Link>
          </div>

          <p className="mt-8 text-xs text-gray-500">
            Referral credits are issued after your first $75+ lesson is completed. FTC disclosure: your friend may receive Theta credits when you book.{' '}
            <Link href="/legal/referrals-terms" className="text-[#7E22CE] underline">
              Terms apply
            </Link>
            .
          </p>
        </section>

        <section className="relative flex-1">
          <div className="mx-auto max-w-md rounded-3xl border border-purple-100 bg-white p-8 shadow-xl">
            <p className="text-sm font-medium text-[#7E22CE]">How it works</p>
            <ul className="mt-6 space-y-4 text-sm text-gray-600">
              <li>
                <span className="font-semibold text-gray-900">1.</span> Use your friend&rsquo;s link to sign up &mdash; no code entry required.
              </li>
              <li>
                <span className="font-semibold text-gray-900">2.</span> Book any $75+ lesson within 30 days to unlock {"$"}20 in credits.
              </li>
              <li>
                <span className="font-semibold text-gray-900">3.</span> Both of you get {"$"}20 in Theta credits for future lessons.
              </li>
            </ul>

            <div className="mt-8 rounded-2xl bg-purple-50 p-4 text-sm text-purple-900">
              Already booked with Theta? Share your link from the <Link href="/rewards" className="font-semibold underline">rewards page</Link> and keep the lessons going.
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
