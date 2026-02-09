import { UNIVERSAL_SKILL_LEVEL_OPTIONS } from '@/components/search/filterTypes';

import {
  buildContentFiltersParam,
  buildSkillLevelParam,
  getDynamicContentFiltersFromTaxonomy,
  getSkillLevelOptionsFromTaxonomy,
  parseContentFiltersParam,
  parseSkillLevelParam,
  resolveSubcategoryContext,
  sanitizeContentFiltersForSubcategory,
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
  it('prioritizes explicit subcategory_id when it is a known id', () => {
    const resolved = resolveSubcategoryContext({
      explicitSubcategoryId: 'sub-2',
      subcategoryParam: 'Math',
      serviceCatalogId: 'svc-1',
      lookup: createLookup(),
    });

    expect(resolved).toEqual({
      resolvedSubcategoryId: 'sub-2',
      inferredSubcategoryId: null,
    });
  });

  it('falls back to service inference when explicit subcategory_id is invalid', () => {
    const resolved = resolveSubcategoryContext({
      explicitSubcategoryId: 'invalid-value',
      serviceCatalogId: 'svc-1',
      lookup: createLookup(),
    });

    expect(resolved).toEqual({
      resolvedSubcategoryId: 'sub-1',
      inferredSubcategoryId: 'sub-1',
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

  it('parses content_filters with dedupe and malformed segment tolerance', () => {
    expect(
      parseContentFiltersParam(
        'goal:enrichment,competition,competition|badsegment|format:one_on_one,,small_group|:oops'
      )
    ).toEqual({
      goal: ['enrichment', 'competition'],
      format: ['one_on_one', 'small_group'],
    });
  });

  it('builds canonical content_filters param in supplied key order', () => {
    expect(
      buildContentFiltersParam(
        {
          format: ['small_group', 'one_on_one'],
          goal: ['competition', 'enrichment'],
        },
        ['goal', 'format']
      )
    ).toBe('goal:competition,enrichment|format:small_group,one_on_one');
  });

  it('sanitizes stale content filter selections against taxonomy definitions', () => {
    const taxonomy = [
      {
        filter_key: 'goal',
        filter_display_name: 'Goal',
        filter_type: 'multi_select',
        options: [
          { id: '1', value: 'enrichment', display_name: 'Enrichment', display_order: 1 },
          { id: '2', value: 'competition', display_name: 'Competition', display_order: 2 },
        ],
      },
      {
        filter_key: 'format',
        filter_display_name: 'Format',
        filter_type: 'multi_select',
        options: [{ id: '3', value: 'one_on_one', display_name: 'One-on-One', display_order: 1 }],
      },
    ];

    expect(
      sanitizeContentFiltersForSubcategory(
        {
          goal: ['enrichment', 'invalid'],
          format: ['one_on_one', 'small_group'],
          style: ['jazz'],
        },
        taxonomy
      )
    ).toEqual({
      goal: ['enrichment'],
      format: ['one_on_one'],
    });
  });

  it('returns empty dynamic filters and selections when no subcategory context exists', () => {
    expect(getDynamicContentFiltersFromTaxonomy(undefined)).toEqual([]);
    expect(sanitizeContentFiltersForSubcategory({ goal: ['enrichment'] }, undefined)).toEqual({});
  });
});
