import Link from 'next/link';

export default function ReferralLandingPage() {
  return (
    <div className="relative overflow-hidden bg-gradient-to-b from-white via-purple-50 to-white">
      <div className="mx-auto flex min-h-[70vh] w-full max-w-5xl flex-col gap-16 px-4 py-16 sm:px-6 lg:flex-row lg:items-center lg:gap-20 lg:px-8">
        <section className="max-w-xl">
          <p className="mb-4 inline-flex items-center rounded-full bg-(--color-brand-dark)/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-(--color-brand-dark)">
            Give $20 · Get $20
          </p>
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-gray-100 sm:text-5xl">
            Book your first $75+ lesson and get $20 off.
          </h1>
          <p className="mt-6 text-base leading-7 text-gray-600 dark:text-gray-400">
            Join iNSTAiNSTRU with a friend&rsquo;s link and save {"$"}20 on your first lesson. Book within 30 days and you&rsquo;ll both earn credits for the next session.
          </p>

          <div className="mt-10 flex flex-col items-start gap-3 sm:flex-row">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center rounded-lg bg-(--color-brand-dark) px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6b1fb8] focus:outline-none "
            >
              Create an account
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center justify-center rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-3 text-sm font-semibold text-gray-700 dark:text-gray-300 transition hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none "
            >
              Open the app
            </Link>
          </div>

          <p className="mt-8 text-xs text-gray-500 dark:text-gray-400">
            Referral credits are issued after your first $75+ lesson is completed. FTC disclosure: your friend may receive iNSTAiNSTRU credits when you book.{' '}
            <Link href="/referrals-terms" className="text-(--color-brand-dark) underline">
              Terms apply
            </Link>
            .
          </p>
        </section>

        <section className="relative flex-1">
          <div className="mx-auto max-w-md rounded-3xl border border-purple-100 bg-white dark:bg-gray-800 p-8 shadow-xl">
            <p className="text-sm font-medium text-(--color-brand-dark)">How it works</p>
            <ul className="mt-6 space-y-4 text-sm text-gray-600 dark:text-gray-400">
              <li>
                <span className="font-semibold text-gray-900 dark:text-gray-100">1.</span> Use your friend&rsquo;s link to sign up &mdash; no code entry required.
              </li>
              <li>
                <span className="font-semibold text-gray-900 dark:text-gray-100">2.</span> Book any $75+ lesson within 30 days to unlock {"$"}20 in credits.
              </li>
              <li>
                <span className="font-semibold text-gray-900 dark:text-gray-100">3.</span> Both of you get {"$"}20 in iNSTAiNSTRU credits for future lessons.
              </li>
            </ul>

            <div className="mt-8 rounded-2xl bg-purple-50 p-4 text-sm text-purple-900">
              Already booked with iNSTAiNSTRU? Share your link from the <Link href="/student/dashboard?tab=rewards" className="font-semibold underline">rewards page</Link> and keep the lessons going.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
