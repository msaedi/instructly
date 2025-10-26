// frontend/types/badges.ts

export type BadgeProgress = {
  current: number;
  goal: number;
  percent: number;
};

export type StudentBadgeItem = {
  slug: string;
  name: string;
  description?: string;
  earned: boolean;
  status?: 'pending' | 'confirmed' | 'revoked';
  awarded_at?: string;
  confirmed_at?: string;
  progress?: BadgeProgress | null;
};

export type AdminAwardBadge = {
  slug: string;
  name: string;
  criteria_type?: string | null;
};

export type AdminAwardStudent = {
  id: string;
  email?: string | null;
  display_name?: string | null;
};

export type AdminAward = {
  award_id: string;
  status: 'pending' | 'confirmed' | 'revoked';
  awarded_at: string;
  hold_until?: string | null;
  confirmed_at?: string | null;
  revoked_at?: string | null;
  badge: AdminAwardBadge;
  student: AdminAwardStudent;
};

export type AdminAwardListResponse = {
  items: AdminAward[];
  total: number;
  next_offset?: number | null;
};
