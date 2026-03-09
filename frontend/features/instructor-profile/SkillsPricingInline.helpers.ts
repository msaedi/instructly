import type { CategoryServiceDetail } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import type { FormatPriceState } from '@/lib/pricing/formatPricing';
import {
  ALL_AUDIENCE_GROUPS,
  DEFAULT_SKILL_LEVELS,
  defaultFilterSelections,
} from '@/lib/taxonomy/filterHelpers';
import type { AudienceGroup, FilterSelections } from '@/lib/taxonomy/filterHelpers';

export type SelectedService = {
  catalog_service_id: string;
  subcategory_id: string;
  service_catalog_name?: string | null;
  name?: string | null;
  format_prices: FormatPriceState;
  eligible_age_groups: AudienceGroup[];
  filter_selections: FilterSelections;
  description?: string;
  equipment?: string;
  duration_options: number[];
};

export const getPendingHydrationAcceptance = ({
  pendingSyncSignature,
  incomingSignature,
  nextSelectedServices,
}: {
  pendingSyncSignature: string | null;
  incomingSignature: string;
  nextSelectedServices: SelectedService[];
}) => {
  if (!pendingSyncSignature || incomingSignature !== pendingSyncSignature) {
    return null;
  }

  return {
    nextPendingSyncSignature: null as null,
    nextHasLocalEdits: false,
    nextIsEditing: false,
    nextIsHydrating: true,
    nextSelectedServices,
  };
};

type MutableCurrent<T> = { current: T };

export const applyPendingHydrationAcceptance = ({
  pendingHydrationAcceptance,
  pendingSyncSignatureRef,
  hasLocalEditsRef,
  isEditingRef,
  isHydratingRef,
  setSelectedServices,
}: {
  pendingHydrationAcceptance: ReturnType<typeof getPendingHydrationAcceptance>;
  pendingSyncSignatureRef: MutableCurrent<string | null>;
  hasLocalEditsRef: MutableCurrent<boolean>;
  isEditingRef: MutableCurrent<boolean>;
  isHydratingRef: MutableCurrent<boolean>;
  setSelectedServices: (services: SelectedService[]) => void;
}): boolean => {
  if (!pendingHydrationAcceptance) {
    return false;
  }

  logger.debug('SkillsPricingInline: hydration matches pending save, accepting', {
    matchedSignature: true,
  });
  pendingSyncSignatureRef.current = pendingHydrationAcceptance.nextPendingSyncSignature;
  hasLocalEditsRef.current = pendingHydrationAcceptance.nextHasLocalEdits;
  isEditingRef.current = pendingHydrationAcceptance.nextIsEditing;
  isHydratingRef.current = pendingHydrationAcceptance.nextIsHydrating;
  setSelectedServices(pendingHydrationAcceptance.nextSelectedServices);
  return true;
};

export type CatalogBackfillSource = Pick<
  CategoryServiceDetail,
  'subcategory_id' | 'eligible_age_groups'
>;

export const backfillSelectedServicesFromCatalog = (
  selectedServices: SelectedService[],
  serviceCatalogById: Map<string, CatalogBackfillSource>,
) => {
  let changed = false;
  const nextSelectedServices = selectedServices.map((svc) => {
    const entry = serviceCatalogById.get(svc.catalog_service_id);
    if (!entry) return svc;

    let updated = svc;
    if (!updated.subcategory_id && entry.subcategory_id) {
      updated = { ...updated, subcategory_id: entry.subcategory_id };
      changed = true;
    }

    const backfillAgeGroups = entry.eligible_age_groups ?? [];
    if (updated.eligible_age_groups.length === 0 && backfillAgeGroups.length > 0) {
      updated = { ...updated, eligible_age_groups: backfillAgeGroups };
      changed = true;
    }

    if (!updated.filter_selections['skill_level'] || !updated.filter_selections['age_groups']) {
      const defaults = defaultFilterSelections(updated.eligible_age_groups);
      const merged = { ...updated.filter_selections };
      if (!merged['skill_level']) merged['skill_level'] = defaults['skill_level'] ?? [...DEFAULT_SKILL_LEVELS];
      if (!merged['age_groups']) merged['age_groups'] = defaults['age_groups'] ?? [...ALL_AUDIENCE_GROUPS];
      updated = { ...updated, filter_selections: merged };
      changed = true;
    }

    return updated;
  });

  return {
    changed,
    nextSelectedServices: changed ? nextSelectedServices : selectedServices,
  };
};
