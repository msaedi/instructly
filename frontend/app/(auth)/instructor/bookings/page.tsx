'use client';

import Link from 'next/link';

export default function InstructorBookingsPage() {
  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">Bookings</h1>
      <p className="text-gray-600 mt-1">Upcoming and past bookings will be displayed here.</p>
      <div className="mt-6">
        <Link href="/instructor/dashboard" className="text-purple-700 hover:underline">Back to dashboard</Link>
      </div>
    </div>
  );
}
