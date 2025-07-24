# Natural Language Search Behavior Specification

## Core Principle
When a user specifies a **particular service**, they should ONLY see instructors who teach that specific service. When they use **general terms** or **category names**, broader results are acceptable.

## Expected Behaviors

### 1. Specific Service Queries (STRICT MATCHING)

When a user mentions a specific service, return ONLY instructors who teach that exact service:

| Query | Should Return | Should NOT Return |
|-------|--------------|-------------------|
| "piano under $80" | ONLY piano instructors ≤ $80 | ❌ Drums, Guitar, Bass, etc. |
| "spanish lessons tomorrow" | ONLY Spanish instructors available tomorrow | ❌ French, Italian, etc. |
| "yoga classes near me" | ONLY yoga instructors nearby | ❌ Pilates, fitness, etc. |
| "SAT prep this weekend" | ONLY SAT tutors available weekend | ❌ ACT, GRE, etc. |

### 2. Category/General Queries (BROAD MATCHING OK)

When a user uses category terms or general language, return all relevant instructors in that category:

| Query | Should Return | Why |
|-------|--------------|-----|
| "music lessons under $50" | ALL music instructors ≤ $50 | "Music" is a category, not a specific service |
| "tutoring help" | ALL tutors | General term, no specific subject |
| "fitness classes" | ALL fitness instructors | Category-level query |
| "lessons under $30" | ALL instructors ≤ $30 | No service specified |

### 3. Multiple Service Queries (UNION)

When a user explicitly mentions multiple services, return instructors who teach ANY of those services:

| Query | Should Return |
|-------|--------------|
| "piano or guitar under $60" | Piano instructors ≤ $60 AND Guitar instructors ≤ $60 |
| "spanish and french teachers" | Spanish instructors AND French instructors |

### 4. Edge Cases & Clarifications

| Scenario | Behavior |
|----------|----------|
| Misspellings | "piono lessons" → Should still match piano (fuzzy matching) |
| Synonyms | "keyboard lessons" → Should match piano if they're linked |
| Partial matches | "drum" → Should match "drums" |
| No service extractable | Default to broad search across all services |

## Algorithm Logic

```python
# CURRENT (WRONG):
if query contains "piano":
    category = get_category("piano")  # Returns "Music"
    return all_instructors_in_category(category) with constraints

# SHOULD BE:
if query contains "piano":
    service = get_service("piano")  # Returns specific service
    return instructors_who_teach(service) with constraints
```

## Test Cases for Verification

### Must Pass - Specific Services
1. ✅ "piano under $80" → Returns ONLY piano instructors ≤ $80
2. ✅ "spanish lessons" → Returns ONLY Spanish instructors
3. ✅ "yoga tomorrow" → Returns ONLY yoga instructors available tomorrow

### Must Pass - Categories
1. ✅ "music lessons" → Returns ALL music instructors (piano, guitar, drums, etc.)
2. ✅ "language tutoring" → Returns ALL language instructors
3. ✅ "cheap lessons" → Returns ALL instructors under price threshold

### Must Pass - Edge Cases
1. ✅ "piano" (no constraints) → Returns ALL piano instructors
2. ✅ "under $50" (no service) → Returns ALL instructors ≤ $50
3. ✅ "tomorrow" (no service) → Returns ALL instructors available tomorrow

## Why This Matters

1. **User Intent**: When someone searches for "piano lessons", they don't want to see drums
2. **Trust**: Precise results build confidence in the platform
3. **Efficiency**: Users shouldn't have to filter through irrelevant results
4. **Fairness**: Popular instruments shouldn't crowd out specific searches

## Implementation Guidance

The fix should:
1. Extract specific service(s) from the query
2. Match instructors who teach THOSE specific services
3. Apply additional constraints (price, time, location)
4. Only broaden to category when no specific service is mentioned

**Key**: The search should be as specific as the user's query. If they say "piano", show piano. If they say "music", show all music.
