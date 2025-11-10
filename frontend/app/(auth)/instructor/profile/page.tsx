'use client';

import { useEmbedded } from '../_embedded/EmbeddedContext';
import InstructorProfileForm from '@/features/instructor-profile/InstructorProfileForm';

export default function InstructorProfilePage() {
  const embedded = useEmbedded();
  return <InstructorProfileForm context="dashboard" embedded={embedded} />;
}
