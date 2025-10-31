import type { Meta, StoryObj } from '@storybook/react';
import WeekView from '@/components/calendar/WeekView';
import { getWeekDates } from '@/lib/availability/dateHelpers';
import type { WeekSchedule } from '@/types/availability';

const baseWeek = getWeekDates(new Date('2025-05-05'));

const baseSchedule: WeekSchedule = {
  '2025-05-05': [
    { start_time: '08:00:00', end_time: '11:00:00' },
    { start_time: '13:00:00', end_time: '16:30:00' },
  ],
  '2025-05-06': [
    { start_time: '09:00:00', end_time: '12:00:00' },
    { start_time: '14:00:00', end_time: '18:00:00' },
  ],
};

const overnightSchedule: WeekSchedule = {
  '2025-05-05': [
    { start_time: '22:30:00', end_time: '01:30:00' },
  ],
};

const containmentSchedule: WeekSchedule = {
  '2025-05-05': [
    { start_time: '09:00:00', end_time: '13:00:00' },
    { start_time: '10:00:00', end_time: '11:00:00' },
  ],
};

const dstWeek = getWeekDates(new Date('2024-03-04'));
const dstSchedule: WeekSchedule = {
  '2024-03-10': [
    { start_time: '01:30:00', end_time: '03:30:00' },
  ],
};

const meta: Meta<typeof WeekView> = {
  title: 'Calendar/WeekView',
  component: WeekView,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    onScheduleChange: () => {},
    startHour: 6,
    endHour: 24,
  },
};

export default meta;

type Story = StoryObj<typeof WeekView>;

export const Normal: Story = {
  args: {
    weekDates: baseWeek,
    schedule: baseSchedule,
  },
};

export const Overnight: Story = {
  args: {
    weekDates: baseWeek,
    schedule: overnightSchedule,
  },
};

export const Containment: Story = {
  args: {
    weekDates: baseWeek,
    schedule: containmentSchedule,
  },
};

export const DST: Story = {
  args: {
    weekDates: dstWeek,
    schedule: dstSchedule,
  },
};

export const MidnightBoundary: Story = {
  args: {
    weekDates: baseWeek,
    schedule: {
      '2025-05-07': [
        { start_time: '18:00:00', end_time: '24:00:00' },
      ],
    },
  },
};
