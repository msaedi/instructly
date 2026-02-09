import { UNIVERSAL_SKILL_LEVEL_OPTIONS } from '@/components/search/filterTypes';

import {
  buildSkillLevelParam,
  getSkillLevelOptionsFromTaxonomy,
  parseSkillLevelParam,
  resolveSubcategoryContext,
  type SubcategoryResolutionLookup,
} from '../filterContext';

const createLookup = (): SubcategoryResolutionLookup => ({
  subcategoryIds: new Set(['sub-1', 'sub-2']),
  subcategoryIdsByLower: new Map([
    ['sub-1', 'sub-1'],
    ['sub-2', 'sub-2'],
  ]),
  subcategoryByName: new Map([
    ['piano lessons', 'sub-1'],
    ['math', 'sub-2'],
  ]),
  serviceByCatalogId: new Map([
    ['svc-1', 'sub-1'],
    ['svc-2', 'sub-2'],
  ]),
  serviceBySlug: new Map([
    ['piano', 'sub-1'],
    ['algebra', 'sub-2'],
  ]),
  serviceByName: new Map([
    ['piano', 'sub-1'],
    ['algebra i', 'sub-2'],
  ]),
});

describe('filterContext helpers', () => {
  it('prioritizes explicit subcategory_id', () => {
    const resolved = resolveSubcategoryContext({
      explicitSubcategoryId: 'sub-explicit',
      subcategoryParam: 'Math',
      serviceCatalogId: 'svc-1',
      lookup: createLookup(),
    });

    expect(resolved).toEqual({
      resolvedSubcategoryId: 'sub-explicit',
      inferredSubcategoryId: null,
    });
  });

  it('resolves subcategory from name when id is not provided', () => {
    const resolved = resolveSubcategoryContext({
      subcategoryParam: 'Piano-Lessons',
      lookup: createLookup(),
    });

    expect(resolved.resolvedSubcategoryId).toBe('sub-1');
    expect(resolved.inferredSubcategoryId).toBeNull();
  });

  it('infers subcategory from service context', () => {
    const resolved = resolveSubcategoryContext({
      serviceCatalogId: 'svc-1',
      lookup: createLookup(),
    });

    expect(resolved).toEqual({
      resolvedSubcategoryId: 'sub-1',
      inferredSubcategoryId: 'sub-1',
    });
  });

  it('falls back to service slug and service name lookup', () => {
    const fromSlug = resolveSubcategoryContext({
      serviceParam: 'piano',
      lookup: createLookup(),
    });
    const fromName = resolveSubcategoryContext({
      serviceName: 'Algebra I',
      lookup: createLookup(),
    });

    expect(fromSlug.resolvedSubcategoryId).toBe('sub-1');
    expect(fromName.resolvedSubcategoryId).toBe('sub-2');
  });

  it('parses skill_level query values with dedupe and validation', () => {
    expect(parseSkillLevelParam('beginner,ADVANCED,foo,advanced')).toEqual([
      'beginner',
      'advanced',
    ]);
    expect(parseSkillLevelParam('')).toEqual([]);
    expect(parseSkillLevelParam(undefined)).toEqual([]);
  });

  it('builds comma-separated skill_level param only for constrained selections', () => {
    const options = UNIVERSAL_SKILL_LEVEL_OPTIONS;
    expect(buildSkillLevelParam([], options)).toBeNull();
    expect(buildSkillLevelParam(['beginner', 'intermediate', 'advanced'], options)).toBeNull();
    expect(buildSkillLevelParam(['beginner', 'advanced'], options)).toBe('beginner,advanced');
  });

  it('derives skill level options from taxonomy with universal fallback', () => {
    const taxonomyOptions = getSkillLevelOptionsFromTaxonomy([
      {
        filter_key: 'skill_level',
        filter_display_name: 'Skill Level',
        filter_type: 'multi_select',
        options: [
          { id: '1', value: 'beginner', display_name: 'Beginner', display_order: 1 },
          { id: '2', value: 'advanced', display_name: 'Advanced', display_order: 2 },
          { id: '3', value: 'invalid', display_name: 'Invalid', display_order: 3 },
        ],
      },
    ]);
    const fallbackOptions = getSkillLevelOptionsFromTaxonomy(undefined);

    expect(taxonomyOptions).toEqual([
      { value: 'beginner', label: 'Beginner' },
      { value: 'advanced', label: 'Advanced' },
    ]);
    expect(fallbackOptions).toEqual(UNIVERSAL_SKILL_LEVEL_OPTIONS);
  });
});
