'use client';

import { useAdminAuth } from '@/hooks/useAdminAuth';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tooltip from '@radix-ui/react-tooltip';
import * as Tabs from '@radix-ui/react-tabs';
import * as Popover from '@radix-ui/react-popover';
import { useState } from 'react';

export default function UIPreviewPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const [open, setOpen] = useState(false);

  if (isLoading) return null;
  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center">
          <h1 className="text-xl font-semibold">UI Preview</h1>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>
          <div className="col-span-12 md:col-span-9 lg:col-span-9">

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Dialog demo */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40">
            <h2 className="text-lg font-semibold mb-3">Dialog</h2>
            <Dialog.Root open={open} onOpenChange={setOpen}>
              <Dialog.Trigger asChild>
                <button className="inline-flex items-center rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:brightness-110">Open Dialog</button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/40" />
                <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-md rounded-xl bg-white dark:bg-gray-900 p-6 shadow-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
                  <Dialog.Title className="text-lg font-semibold mb-2">Sample Dialog</Dialog.Title>
                  <Dialog.Description className="text-sm text-gray-600 dark:text-gray-400 mb-4">This is an unstyled Radix dialog controlled with Tailwind.</Dialog.Description>
                  <div className="text-right">
                    <Dialog.Close asChild>
                      <button className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60">Close</button>
                    </Dialog.Close>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>

          {/* Tabs + Tooltip + Popover demo */}
          <div className="rounded-2xl p-6 shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40">
            <h2 className="text-lg font-semibold mb-3">Tabs, Tooltip, Popover</h2>
            <Tabs.Root defaultValue="one">
              <Tabs.List className="inline-flex gap-2 mb-4">
                <Tabs.Trigger value="one" className="px-3 py-1.5 rounded-full ring-1 ring-gray-300/70 data-[state=active]:bg-indigo-600 data-[state=active]:text-white">One</Tabs.Trigger>
                <Tabs.Trigger value="two" className="px-3 py-1.5 rounded-full ring-1 ring-gray-300/70 data-[state=active]:bg-indigo-600 data-[state=active]:text-white">Two</Tabs.Trigger>
              </Tabs.List>
              <Tabs.Content value="one" className="text-sm text-gray-700 dark:text-gray-300">
                <Tooltip.Provider>
                  <Tooltip.Root>
                    <Tooltip.Trigger asChild>
                      <button className="rounded-full px-3 py-1.5 ring-1 ring-gray-300/70 hover:bg-gray-50 dark:hover:bg-gray-800">Hover me</button>
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content side="top" sideOffset={8} className="rounded-md bg-gray-900 text-white px-2 py-1 text-xs shadow pointer-events-none select-none">Tooltip example</Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                </Tooltip.Provider>
              </Tabs.Content>
              <Tabs.Content value="two" className="text-sm text-gray-700 dark:text-gray-300">
                <Popover.Root>
                  <Popover.Trigger asChild>
                    <button className="rounded-full px-3 py-1.5 ring-1 ring-gray-300/70 hover:bg-gray-50 dark:hover:bg-gray-800">Open popover</button>
                  </Popover.Trigger>
                  <Popover.Portal>
                    <Popover.Content sideOffset={8} className="rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white dark:bg-gray-900 p-3 text-xs shadow">
                      Popover content here
                    </Popover.Content>
                  </Popover.Portal>
                </Popover.Root>
              </Tabs.Content>
            </Tabs.Root>
          </div>
        </div>
          </div>
        </div>
      </main>
    </div>
  );
}
