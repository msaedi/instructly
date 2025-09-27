export default function ReferralTermsPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
      <header className="mb-8">
        <p className="text-sm uppercase tracking-[0.18em] text-gray-500">Instainstru Legal</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-900">Referral Program Terms</h1>
        <p className="mt-3 text-sm text-gray-600">
          Last updated {new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
        </p>
      </header>

      <section className="space-y-6 text-sm leading-6 text-gray-700">
        <p>
          These Referral Program Terms (&ldquo;Terms&rdquo;) govern participation in the Instainstru &ldquo;Give $20 / Get $20&rdquo; referral offer. They work together with our
          <a href="/legal/terms" className="text-[#7E22CE] underline"> Terms of Service</a> and
          <a href="/legal/privacy" className="text-[#7E22CE] underline"> Privacy Notice</a>. By sharing a referral link or redeeming a referral reward, you agree to these Terms.
        </p>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Eligibility</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>Referrers must have an active Instainstru account in good standing.</li>
            <li>New students (the &ldquo;referee&rdquo;) must create a Instainstru account using the referrer&rsquo;s link and complete their first $75+ lesson within 30 days of signup.</li>
            <li>Referral credits are issued only once per referee household. Duplicate or self-referrals are not permitted.</li>
          </ul>
        </article>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Earning Rewards</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>When the referee completes an eligible lesson, both the referrer and referee receive $20 in Instainstru credits.</li>
            <li>Credits are typically issued within 48 hours of the lesson completion.</li>
            <li>If a lesson is canceled or refunded, associated referral credits may be revoked.</li>
          </ul>
        </article>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Using Credits</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>Referral credits apply automatically at checkout when you have at least $75 in eligible lesson fees and no other promotions are active.</li>
            <li>Credits have no cash value, are non-transferable, and may be used only on the Instainstru platform.</li>
            <li>Only one referral credit can be applied per order. Credits cannot be combined with promo codes or other offers.</li>
          </ul>
        </article>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Expiration &amp; Forfeiture</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>Referral credits expire as noted in your rewards dashboard (currently 90 days from issuance unless stated otherwise).</li>
            <li>Unused credits are forfeited upon expiration, account closure, or violation of these Terms.</li>
          </ul>
        </article>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Fair Use</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            <li>We may suspend or revoke referral privileges for suspected fraud, spam, reseller activity, or other abuse.</li>
            <li>Referral links may not be shared on coupon sites or paid ad networks without Instainstru&rsquo;s written consent.</li>
          </ul>
        </article>

        <article>
          <h2 className="text-lg font-semibold text-gray-900">Changes &amp; Contact</h2>
          <p className="mt-3">
            Instainstru may update or discontinue the referral program at any time. We will honor credits already issued unless the program ends due to abuse. Questions? Contact support@instainstrucoach.com.
          </p>
        </article>
      </section>
    </main>
  );
}
