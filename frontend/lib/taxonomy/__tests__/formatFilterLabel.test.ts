import { formatFilterLabel } from '../formatFilterLabel';

describe('formatFilterLabel', () => {
  it('returns special-case label for known keys', () => {
    expect(formatFilterLabel('ap')).toBe('AP');
    expect(formatFilterLabel('ib')).toBe('IB');
    expect(formatFilterLabel('adhd')).toBe('ADHD');
    expect(formatFilterLabel('iep_support')).toBe('IEP Support');
    expect(formatFilterLabel('esl')).toBe('ESL');
    expect(formatFilterLabel('pre_k')).toBe('Pre-K');
    expect(formatFilterLabel('one_on_one')).toBe('One-on-One');
    expect(formatFilterLabel('self_defense')).toBe('Self-Defense');
    expect(formatFilterLabel('homework_help')).toBe('Homework Help');
    expect(formatFilterLabel('college_prep')).toBe('College Prep');
  });

  it('is case-insensitive', () => {
    expect(formatFilterLabel('AP')).toBe('AP');
    expect(formatFilterLabel('IEP_SUPPORT')).toBe('IEP Support');
    expect(formatFilterLabel('Pre_K')).toBe('Pre-K');
  });

  it('trims whitespace', () => {
    expect(formatFilterLabel('  ap  ')).toBe('AP');
  });

  it('uses displayName when provided and value is not a special case', () => {
    expect(formatFilterLabel('custom_thing', 'My Custom Label')).toBe('My Custom Label');
  });

  it('prefers special-case label over displayName', () => {
    expect(formatFilterLabel('ap', 'Advanced Placement')).toBe('AP');
  });

  it('falls back to title-case conversion for unknown values', () => {
    expect(formatFilterLabel('beginner')).toBe('Beginner');
    expect(formatFilterLabel('some_long_value')).toBe('Some Long Value');
  });

  it('handles empty string gracefully', () => {
    expect(formatFilterLabel('')).toBe('');
  });

  it('handles displayName that is empty or whitespace-only', () => {
    expect(formatFilterLabel('beginner', '')).toBe('Beginner');
    expect(formatFilterLabel('beginner', '   ')).toBe('Beginner');
    expect(formatFilterLabel('beginner', null)).toBe('Beginner');
  });
});
