// frontend/types/badges.ts
// Re-export badge-related models from the OpenAPI type shim.

export type {
  BadgeProgressView as BadgeProgress,
  StudentBadgeView as StudentBadgeItem,
  AdminAwardBadgeSchema as AdminAwardBadge,
  AdminAwardStudentSchema as AdminAwardStudent,
  AdminAwardSchema as AdminAward,
  AdminAwardListResponse,
} from '@/features/shared/api/types';
