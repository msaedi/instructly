const SPECIAL_FILTER_OPTION_LABELS: Record<string, string> = {
  pre_k: 'Pre-K',
  ap: 'AP',
  ib: 'IB',
  adhd: 'ADHD',
  iep_support: 'IEP Support',
  esl: 'ESL',
  homework_help: 'Homework Help',
  test_prep: 'Test Prep',
  audition_prep: 'Audition Prep',
  college_prep: 'College Prep',
  career_prep: 'Career Prep',
  middle_school: 'Middle School',
  high_school: 'High School',
  small_group: 'Small Group',
  one_on_one: 'One-on-One',
  one_time: 'One-time',
  dyslexia_reading: 'Dyslexia/Reading',
  executive_function: 'Executive Function',
  heritage_speaker: 'Heritage Speaker',
  school_support: 'School Support',
  self_defense: 'Self-Defense',
  learning_differences: 'Learning Differences',
  new_learner: 'New Learner',
};

const titleCaseFromKey = (value: string): string =>
  value
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(' ');

export const formatFilterLabel = (value: string, displayName?: string | null): string => {
  const normalized = value.trim().toLowerCase();
  if (SPECIAL_FILTER_OPTION_LABELS[normalized]) {
    return SPECIAL_FILTER_OPTION_LABELS[normalized];
  }
  if (displayName && displayName.trim().length > 0) {
    return displayName;
  }
  return titleCaseFromKey(normalized);
};
