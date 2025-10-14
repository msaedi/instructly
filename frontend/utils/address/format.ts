const STATE_NAME_TO_CODE: Record<string, string> = {
  'Alabama': 'AL',
  'Alaska': 'AK',
  'Arizona': 'AZ',
  'Arkansas': 'AR',
  'California': 'CA',
  'Colorado': 'CO',
  'Connecticut': 'CT',
  'Delaware': 'DE',
  'District of Columbia': 'DC',
  'Florida': 'FL',
  'Georgia': 'GA',
  'Hawaii': 'HI',
  'Idaho': 'ID',
  'Illinois': 'IL',
  'Indiana': 'IN',
  'Iowa': 'IA',
  'Kansas': 'KS',
  'Kentucky': 'KY',
  'Louisiana': 'LA',
  'Maine': 'ME',
  'Maryland': 'MD',
  'Massachusetts': 'MA',
  'Michigan': 'MI',
  'Minnesota': 'MN',
  'Mississippi': 'MS',
  'Missouri': 'MO',
  'Montana': 'MT',
  'Nebraska': 'NE',
  'Nevada': 'NV',
  'New Hampshire': 'NH',
  'New Jersey': 'NJ',
  'New Mexico': 'NM',
  'New York': 'NY',
  'North Carolina': 'NC',
  'North Dakota': 'ND',
  'Ohio': 'OH',
  'Oklahoma': 'OK',
  'Oregon': 'OR',
  'Pennsylvania': 'PA',
  'Rhode Island': 'RI',
  'South Carolina': 'SC',
  'South Dakota': 'SD',
  'Tennessee': 'TN',
  'Texas': 'TX',
  'Utah': 'UT',
  'Vermont': 'VT',
  'Virginia': 'VA',
  'Washington': 'WA',
  'West Virginia': 'WV',
  'Wisconsin': 'WI',
  'Wyoming': 'WY',
};

export function toStateCode(state?: string): string {
  if (!state) return '';
  const trimmed = state.trim();
  if (!trimmed) return '';
  if (/^[A-Za-z]{2,3}$/.test(trimmed)) {
    return trimmed.toUpperCase();
  }
  return STATE_NAME_TO_CODE[trimmed] ?? trimmed;
}

export function formatMeetingLocation(
  line1?: string,
  city?: string,
  state?: string,
  postal?: string,
): string {
  const normalizedLine1 = line1?.trim() || '';
  const normalizedCity = city?.trim() || '';
  const normalizedState = toStateCode(state);
  const normalizedPostal = postal?.trim() || '';

  const statePostal = [normalizedState, normalizedPostal].filter((part) => part.length > 0).join(' ').trim();

  const trimmed = [normalizedLine1, normalizedCity, statePostal].filter((part) => part.length > 0);

  const deduped = trimmed.filter((part, index, array) => index === 0 || part !== array[index - 1]);

  return deduped.join(', ');
}
