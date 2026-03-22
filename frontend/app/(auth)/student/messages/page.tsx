'use client';

import { MessagesPanelContent } from '@/app/(auth)/instructor/messages/page';
import { StudentHeader } from '@/components/layout/StudentHeader';

export default function StudentMessagesPage() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <StudentHeader />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <MessagesPanelContent viewerRole="student" />
      </main>
    </div>
  );
}
