'use client';

import type { ComponentProps } from 'react';
import TimeSelectionModal from '../components/TimeSelectionModal';

export type TimeSelectionFacadeProps = ComponentProps<typeof TimeSelectionModal>;

export default function TimeSelectionFacade(props: TimeSelectionFacadeProps) {
  return <TimeSelectionModal {...props} />;
}
