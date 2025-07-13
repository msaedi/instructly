/**
 * Natural Language Search Parser
 *
 * Parses natural language search queries into structured search parameters.
 * Examples:
 * - "Math tutor under $50" → { subjects: ['math'], max_rate: 50 }
 * - "Spanish teacher available now" → { subjects: ['spanish'], available_now: true }
 * - "Piano lessons tomorrow at 3pm" → { subjects: ['piano'], date: '2024-01-11', start_time: '15:00' }
 */

interface ParsedSearch {
  subjects: string[];
  min_rate?: number;
  max_rate?: number;
  available_now?: boolean;
  date?: string;
  start_time?: string;
  end_time?: string;
}

/**
 * Subject keywords mapping to standardized subjects
 */
const SUBJECT_KEYWORDS: Record<string, string[]> = {
  math: ['math', 'mathematics', 'algebra', 'geometry', 'calculus', 'trigonometry'],
  english: ['english', 'writing', 'literature', 'reading', 'grammar'],
  science: ['science', 'physics', 'chemistry', 'biology'],
  spanish: ['spanish', 'español'],
  french: ['french', 'français'],
  music: ['music'],
  piano: ['piano', 'keyboard'],
  guitar: ['guitar'],
  violin: ['violin', 'fiddle'],
  drums: ['drums', 'percussion'],
  singing: ['singing', 'voice', 'vocal'],
  programming: ['programming', 'coding', 'javascript', 'python', 'java', 'computer'],
  test_prep: ['sat', 'act', 'gre', 'gmat', 'test prep', 'test preparation'],
  fitness: ['fitness', 'yoga', 'pilates', 'personal training', 'workout'],
  language: ['language', 'languages'],
};

/**
 * Price keywords and patterns
 */
const PRICE_PATTERNS = {
  under: /under\s*\$?(\d+)/i,
  below: /below\s*\$?(\d+)/i,
  less_than: /less\s+than\s*\$?(\d+)/i,
  max: /max\s*\$?(\d+)/i,
  above: /above\s*\$?(\d+)/i,
  over: /over\s*\$?(\d+)/i,
  more_than: /more\s+than\s*\$?(\d+)/i,
  min: /min\s*\$?(\d+)/i,
  range: /\$?(\d+)\s*-\s*\$?(\d+)/,
};

/**
 * Time keywords
 */
const TIME_KEYWORDS = {
  now: ['now', 'right now', 'immediately', 'available now'],
  today: ['today'],
  tomorrow: ['tomorrow'],
  morning: ['morning', 'am'],
  afternoon: ['afternoon', 'pm'],
  evening: ['evening', 'night'],
};

/**
 * Parse natural language search query
 */
export function parseSearchQuery(query: string): ParsedSearch {
  const result: ParsedSearch = {
    subjects: [],
  };

  const lowerQuery = query.toLowerCase();

  // Extract subjects
  for (const [subject, keywords] of Object.entries(SUBJECT_KEYWORDS)) {
    if (keywords.some((keyword) => lowerQuery.includes(keyword))) {
      result.subjects.push(subject);
    }
  }

  // Extract price constraints
  for (const [type, pattern] of Object.entries(PRICE_PATTERNS)) {
    const match = lowerQuery.match(pattern);
    if (match) {
      if (type === 'range' && match[1] && match[2]) {
        result.min_rate = parseInt(match[1]);
        result.max_rate = parseInt(match[2]);
      } else if (['under', 'below', 'less_than', 'max'].includes(type) && match[1]) {
        result.max_rate = parseInt(match[1]);
      } else if (['above', 'over', 'more_than', 'min'].includes(type) && match[1]) {
        result.min_rate = parseInt(match[1]);
      }
    }
  }

  // Check for availability now
  if (TIME_KEYWORDS.now.some((keyword) => lowerQuery.includes(keyword))) {
    result.available_now = true;
  }

  // Parse date references
  const today = new Date();
  if (TIME_KEYWORDS.today.some((keyword) => lowerQuery.includes(keyword))) {
    result.date = formatDate(today);
  } else if (TIME_KEYWORDS.tomorrow.some((keyword) => lowerQuery.includes(keyword))) {
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    result.date = formatDate(tomorrow);
  }

  // Parse time references
  const timeMatch = lowerQuery.match(/(\d{1,2})\s*(am|pm)/i);
  if (timeMatch) {
    const hour = parseInt(timeMatch[1]);
    const isPM = timeMatch[2].toLowerCase() === 'pm';
    const hour24 = isPM && hour !== 12 ? hour + 12 : !isPM && hour === 12 ? 0 : hour;
    result.start_time = `${hour24.toString().padStart(2, '0')}:00`;
  } else {
    // Check for general time periods
    if (TIME_KEYWORDS.morning.some((keyword) => lowerQuery.includes(keyword))) {
      result.start_time = '08:00';
      result.end_time = '12:00';
    } else if (TIME_KEYWORDS.afternoon.some((keyword) => lowerQuery.includes(keyword))) {
      result.start_time = '12:00';
      result.end_time = '17:00';
    } else if (TIME_KEYWORDS.evening.some((keyword) => lowerQuery.includes(keyword))) {
      result.start_time = '17:00';
      result.end_time = '21:00';
    }
  }

  return result;
}

/**
 * Format date to YYYY-MM-DD
 */
function formatDate(date: Date): string {
  const year = date.getFullYear();
  const month = (date.getMonth() + 1).toString().padStart(2, '0');
  const day = date.getDate().toString().padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Build search params from parsed query
 */
export function buildSearchParams(
  parsedQuery: ParsedSearch,
  additionalParams?: Record<string, any>
): Record<string, any> {
  const params: Record<string, any> = {};

  if (parsedQuery.subjects.length > 0) {
    params.subjects = parsedQuery.subjects;
  }

  if (parsedQuery.min_rate !== undefined) {
    params.min_rate = parsedQuery.min_rate;
  }

  if (parsedQuery.max_rate !== undefined) {
    params.max_rate = parsedQuery.max_rate;
  }

  if (parsedQuery.available_now) {
    params.available_now = true;
  }

  if (parsedQuery.date) {
    params.date = parsedQuery.date;
  }

  if (parsedQuery.start_time) {
    params.start_time = parsedQuery.start_time;
  }

  if (parsedQuery.end_time) {
    params.end_time = parsedQuery.end_time;
  }

  return { ...params, ...additionalParams };
}
