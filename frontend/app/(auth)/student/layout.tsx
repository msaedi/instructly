import { StudentHeader } from '@/components/layout/StudentHeader';

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <StudentHeader />
      {children}
    </>
  );
}
