'use client';

import Link from 'next/link';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ArrowLeft, Settings } from 'lucide-react';

export default function InstructorSettingsPage() {
  return (
    <div className="min-h-screen">
      <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-0 sm:pr-4">
            <UserProfileDropdown />
          </div>
        </div>
        <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
          <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
            <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto">
              <ArrowLeft className="w-4 h-4" />
              <span>Back to dashboard</span>
            </Link>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="sm:hidden mb-2">
          <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
            <ArrowLeft className="w-5 h-5" />
            <span className="sr-only">Back to dashboard</span>
          </Link>
        </div>
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Settings className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-800">Settings</h1>
                <p className="text-sm text-gray-600">Manage your account and preferences</p>
              </div>
            </div>
            <span className="hidden sm:inline" />
          </div>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Account Settings</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Profile Information</h3>
                <p className="text-sm text-gray-500">Update your personal details and bio</p>
              </div>
              <Link
                href="/instructor/profile"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Skills & Pricing</h3>
                <p className="text-sm text-gray-500">Manage your services and hourly rates</p>
              </div>
              <Link
                href="/instructor/onboarding/skill-selection"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Service Areas</h3>
                <p className="text-sm text-gray-500">Set where you can teach</p>
              </div>
              <Link
                href="/instructor/onboarding/skill-selection"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Availability</h3>
                <p className="text-sm text-gray-500">Set your weekly schedule</p>
              </div>
              <Link
                href="/instructor/availability"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Payment Setup</h3>
                <p className="text-sm text-gray-500">Manage your Stripe account and payouts</p>
              </div>
              <Link
                href="/instructor/onboarding/payment-setup"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
            <div className="flex items-center justify-between py-3">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Identity Verification</h3>
                <p className="text-sm text-gray-500">Verify your identity and background check</p>
              </div>
              <Link
                href="/instructor/onboarding/verification"
                className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
              >
                Edit
              </Link>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Preferences</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between py-3 border-b border-gray-100">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Notifications</h3>
                <p className="text-sm text-gray-500">Manage email and push notifications</p>
              </div>
              <button className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium">
                Configure
              </button>
            </div>
            <div className="flex items-center justify-between py-3">
              <div>
                <h3 className="text-sm font-medium text-gray-900">Privacy</h3>
                <p className="text-sm text-gray-500">Control your privacy settings</p>
              </div>
              <button className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium">
                Configure
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
