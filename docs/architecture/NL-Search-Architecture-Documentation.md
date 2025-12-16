# InstaInstru Natural Language Search Architecture
*Last Updated: December 2025*

## Overview

InstaInstru's Natural Language Search (NL Search) allows students to find instructors using everyday language. Instead of filling out forms with filters, users simply type what they're looking for:

```
"cheap piano lessons for my 8 year old in brooklyn tomorrow morning"
```

The system parses this into structured constraints, finds matching instructors, and returns ranked results—all in under 500ms.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER QUERY                                      │
│            "piano lessons for kids in ues tomorrow at 6am under $80"        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           1. CACHE CHECK                                     │
│                     Is this exact query cached?                              │
│                         Hit → Return immediately                             │
│                         Miss → Continue pipeline                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           2. QUERY PARSING                                   │
│  ┌─────────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌───────────────┐  │
│  │   Service   │ │ Location │ │   Date   │ │   Time    │ │    Price      │  │
│  │   "piano"   │ │  "ues"   │ │ tomorrow │ │  6am-7am  │ │   max $80     │  │
│  └─────────────┘ └──────────┘ └──────────┘ └───────────┘ └───────────────┘  │
│  ┌─────────────┐ ┌──────────┐                                                │
│  │  Audience   │ │  Skill   │                                                │
│  │   "kids"    │ │    -     │                                                │
│  └─────────────┘ └──────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      3. LOCATION RESOLUTION (5 Tiers)                        │
│                                                                              │
│   "ues" → Tier 2 (Alias) → "Upper East Side (Carnegie Hill, Lenox Hill,    │
│                             Yorkville)" [AMBIGUOUS - 3 sub-neighborhoods]    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          4. CANDIDATE RETRIEVAL                              │
│                                                                              │
│   Semantic Search (pgvector) + Text Search (pg_trgm)                        │
│   → Find instructors teaching "piano" → 30 candidates                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           5. CONSTRAINT FILTERING                            │
│                                                                              │
│   Initial: 30 → Price ≤$80: 25 → Location (UES): 8 → Availability: 3       │
│                                                                              │
│   If results < 5: Intelligent Relaxation                                    │
│   Relax time → date → location → price (in order)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              6. RANKING                                      │
│                                                                              │
│   Score = 0.35×relevance + 0.25×quality + 0.15×distance +                   │
│           0.10×price_fit + 0.10×freshness + 0.05×completeness               │
│           + audience_boost + skill_boost                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           7. CACHE & RESPOND                                 │
│                                                                              │
│   Cache result (5 min TTL) → Return to user                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Query Parsing

The parser extracts structured constraints from natural language using regex patterns. Constraints are extracted in a specific order to avoid conflicts.

### Extraction Order

1. **Time phrases with "in"** (e.g., "in the morning") - extracted first to prevent location capture
2. **Specific times** (e.g., "at 6am", "around 3pm")
3. **Time-of-day words** (e.g., "morning", "evening")
4. **Date expressions** (e.g., "tomorrow", "next tuesday")
5. **Location** (e.g., "in brooklyn", "near ues")
6. **Price** (e.g., "under $50", "cheap")
7. **Audience** (e.g., "for kids", "for my 8 year old")
8. **Skill level** (e.g., "beginner", "advanced")
9. **Service** (remaining text after extraction)

### Parsing Examples

#### Example 1: Full Query
```
Query: "cheap piano lessons for my 8 year old in brooklyn tomorrow morning"

Parsed:
  service_query: "piano lessons"
  location: "brooklyn"
  date: 2025-12-16 (tomorrow)
  time_after: "06:00"
  time_before: "12:00"
  max_price: null (but "cheap" flags low-price preference)
  audience: "kids"
  skill_level: null
```

#### Example 2: Time Parsing
```
Query: "guitar at 6am"
→ time_after: "06:00", time_before: "07:00" (1-hour window)

Query: "yoga in the morning"
→ time_after: "06:00", time_before: "12:00"

Query: "piano this evening"
→ time_after: "17:00", time_before: "21:00"

Query: "drums around 3pm"
→ time_after: "14:00", time_before: "16:00" (±1 hour)
```

#### Example 3: "In the Morning" vs Location
```
Query: "piano in ues tomorrow in the morning"

❌ BAD (old behavior): location = "ues in the" (captured too much)
✅ GOOD (fixed): location = "ues", time = morning (06:00-12:00)

Fix: Time phrases with "in" are extracted BEFORE location parsing.
```

#### Example 4: Price Parsing
```
Query: "lessons under $50"     → max_price: 50
Query: "cheap guitar lessons"  → max_price: 60 (default for "cheap")
Query: "affordable piano"      → max_price: 80 (default for "affordable")
Query: "budget violin lessons" → max_price: 60
Query: "max $100"              → max_price: 100
```

#### Example 5: Audience Parsing
```
Query: "for kids"           → audience: "kids"
Query: "for my 8 year old"  → audience: "kids" (age < 13)
Query: "for adults"         → audience: "adults"
Query: "for beginners"      → skill_level: "beginner"
Query: "advanced lessons"   → skill_level: "advanced"
```

#### Example 6: Typo Correction
```
Query: "paino lessons"  → service_query: "piano" (corrected via pg_trgm)
Query: "guittar"        → service_query: "guitar"
Query: "viloin"         → service_query: "violin"
```

---

## 2. Location Resolution (5 Tiers)

Location resolution converts user input into official NYC neighborhood boundaries (NTAs). The system tries each tier in order until a match is found.

### Tier Overview

| Tier | Method | Speed | Example |
|------|--------|-------|---------|
| 1 | Exact Match | <1ms | "Upper East Side-Carnegie Hill" |
| 2 | Alias Lookup | <1ms | "ues" → Upper East Side |
| 2.5 | Substring Match | <5ms | "carnegie" → Carnegie Hill |
| 3 | Fuzzy (pg_trgm) | <10ms | "upper easy side" → Upper East Side |
| 4 | Embedding (pgvector) | <100ms | "museum mile" → Upper East Side |
| 5 | LLM (GPT-5-nano) | <500ms | "near the met" → Upper East Side |

### Tier 1: Exact Match

Direct lookup against `region_boundaries.name`.

```
Query: "piano in Upper East Side-Carnegie Hill"
Tier 1: ✅ Exact match found
Result: ["Upper East Side-Carnegie Hill"]
```

### Tier 2: Alias Lookup

Lookup in `location_aliases` table (manually seeded + learned).

```
Query: "piano in ues"
Tier 1: ❌ No exact match for "ues"
Tier 2: ✅ Alias found: "ues" → AMBIGUOUS

Result: ["Upper East Side-Carnegie Hill", "Lenox Hill-Roosevelt Island", "Yorkville"]
Display: "Upper East Side (Carnegie Hill, Lenox Hill-Roosevelt Island, Yorkville)"
```

**Common Aliases:**
| Alias | Resolves To |
|-------|-------------|
| ues | Upper East Side (3 sub-neighborhoods) |
| uws | Upper West Side (2 sub-neighborhoods) |
| les | Lower East Side |
| fidi | Financial District |
| bk | Brooklyn (borough) |
| soho | SoHo |
| tribeca | Tribeca |
| hells kitchen | Clinton |

### Tier 2.5: Substring Match

Checks if input is a substring of any region name.

```
Query: "piano near carnegie"
Tier 1: ❌ No exact match
Tier 2: ❌ No alias for "carnegie"
Tier 2.5: ✅ Substring match: "carnegie" in "Upper East Side-Carnegie Hill"

Result: ["Upper East Side-Carnegie Hill"]
```

### Tier 3: Fuzzy Match (pg_trgm)

Uses PostgreSQL trigram similarity for typo tolerance.

```
Query: "piano in uper east side"
Tier 1: ❌ No exact match
Tier 2: ❌ No alias
Tier 2.5: ❌ No substring
Tier 3: ✅ Fuzzy match (similarity: 0.72 > 0.4 threshold)

Result: ["Upper East Side-Carnegie Hill"]
```

**Threshold:** 0.4 (40% similarity required)

```
Query: "piano in brooklin"
Tier 3: "brooklin" ≈ "Brooklyn" (similarity: 0.65) ✅
→ Returns Brooklyn neighborhoods
```

### Tier 4: Embedding Similarity (pgvector)

Semantic matching using OpenAI embeddings. Finds conceptually similar locations.

```
Query: "piano near museum mile"
Tier 1: ❌ "museum mile" not an official name
Tier 2: ❌ No alias
Tier 2.5: ❌ No substring
Tier 3: ❌ Fuzzy score 0.18 < 0.4 threshold
Tier 4: ✅ Embedding similarity 0.84 > 0.82 threshold

"museum mile" embedding ≈ "Upper East Side-Carnegie Hill" embedding
Result: ["Upper East Side-Carnegie Hill"]
```

**Threshold:** 0.82 (raised from 0.7 to prevent false positives)

**Guard:** If Tier 3 fuzzy score < 0.25, skip Tier 4 (prevents "madeupplace" → random match)

### Tier 5: LLM Resolution (GPT-5-nano)

For complex queries that need interpretation.

```
Query: "piano near the met"
Tier 1-4: ❌ All failed
Tier 5: ✅ LLM interprets "the met" = Metropolitan Museum = Upper East Side

Prompt: "User is looking for 'near the met' in NYC. Which neighborhood?"
Response: {"region": "Upper East Side-Carnegie Hill", "confidence": 0.9}
Result: ["Upper East Side-Carnegie Hill"]
```

**Caching:** LLM results are cached in `location_aliases` (source='llm', status='pending_review')

### Tier Fallthrough: Unresolved

When all tiers fail, the query is tracked for learning.

```
Query: "piano in madeupplace"
Tier 1: ❌ Not a region name
Tier 2: ❌ Not an alias
Tier 2.5: ❌ Not a substring
Tier 3: ❌ Fuzzy score 0.12 < 0.4
Tier 4: ⏭️ SKIPPED (fuzzy score 0.12 < 0.25 guard)
Tier 5: ❌ LLM says "unknown location"

Result: location_not_found = true
Action: Tracked in `unresolved_location_queries` for self-learning
```

### Borough Handling

Borough names expand to all neighborhoods within.

```
Query: "piano in brooklyn"
→ Expands to all Brooklyn neighborhoods
→ ~50 region boundaries matched
```

### Ambiguous Location Display

When a location maps to multiple regions:

```
Query: "violin in ues"
Resolved: ["Carnegie Hill", "Lenox Hill-Roosevelt Island", "Yorkville"]
Display: "Upper East Side (Carnegie Hill, Lenox Hill-Roosevelt Island, Yorkville)"
```

---

## 3. Candidate Retrieval

### Hybrid Retrieval: Semantic + Text

Retrieval uses **two methods** and merges results:

#### Semantic Search (pgvector)
- Embeds the service query using OpenAI text-embedding-3-small
- Finds services with similar embeddings
- Good for conceptual matches ("vocal training" ≈ "singing lessons")

#### Text Search (pg_trgm)
- PostgreSQL trigram similarity
- Good for exact matches and typos
- Prevents semantic drift ("violin" returning "bass guitar")

### Lexical Guardrail

For short, specific queries (≤2 words), we require trigram match to prevent semantic drift:

```
Query: "violin"

Semantic results: [Violin, Bass Guitar, Cello, Viola]
Trigram filter: Only keep if trigram matches "violin"
Final: [Violin] ✅

Without guardrail: "Bass Guitar" might rank high due to
"string instrument" semantic similarity → Bad UX!
```

### Retrieval Example

```
Query: "piano lessons for kids"
Service Query: "piano"

Semantic Search (pgvector):
  1. Piano Lessons (similarity: 0.95)
  2. Keyboard Lessons (similarity: 0.82)
  3. Music Theory (similarity: 0.71)

Text Search (pg_trgm):
  1. Piano Lessons (similarity: 1.0)
  2. Piano for Beginners (similarity: 0.85)

Merged & Deduplicated: 30 candidates
```

---

## 4. Constraint Filtering

### Filter Pipeline

```
Initial Candidates: 30
    │
    ▼ Price Filter (≤ $80)
After Price: 25
    │
    ▼ Location Filter (UES regions)
After Location: 8
    │
    ▼ Audience Filter (teaches kids)
After Audience: 6
    │
    ▼ Availability Filter (tomorrow 6-7am)
After Availability: 2
    │
    ▼ Final Results: 2
```

### Intelligent Relaxation

When results < 5, constraints are relaxed **in priority order**:

| Priority | Constraint | Why Relax First |
|----------|------------|-----------------|
| 1 | Time | Users flexible on exact time |
| 2 | Date | Can book different day |
| 3 | Skill Level | Most teach all levels |
| 4 | Audience | Many teach kids & adults |
| 5 | Location | Still want nearby |
| 6 | Price | Budget is usually firm |

**Never relaxed:** Service type (piano stays piano)

### Relaxation Example

```
Query: "violin in lic tomorrow at 6am"

Initial: 30 candidates
After Location (LIC): 0 ← No instructors in LIC!

Relaxation kicks in:
  Relax time (6am → any): still 0
  Relax date (tomorrow → any): still 0
  Relax location (LIC → nearby): 5 results!

Message: "Showing 5 results from nearby areas.
          No instructors found in Long Island City.
          Relaxed: time, date, location."
```

### Location Filter: Respecting Matches

If location filter passes (has matches), we DON'T pad with non-matching results:

```
Query: "piano in ues tomorrow at 6am"

After Location: 1 (Sarah C. in UES) ✅
After Availability: 1

Even though < 5 results, we DON'T add instructors outside UES.
Location was specified AND matched → respect the user's intent.

Message: "Relaxed: time, date" (NOT location)
```

---

## 5. Ranking

### Ranking Formula

```
final_score = (
    0.35 × relevance_score +      # How well service matches query
    0.25 × quality_score +        # Bayesian-averaged ratings
    0.15 × distance_score +       # Proximity to user/search location
    0.10 × price_score +          # Budget fit
    0.10 × freshness_score +      # Recent activity
    0.05 × completeness_score     # Profile completeness
) + audience_boost + skill_boost
```

### Score Components

#### Relevance Score (35%)
- Combined semantic + text similarity
- Higher if service name closely matches query

#### Quality Score (25%)
- Bayesian average: `(sum_ratings + prior_mean × prior_weight) / (count + prior_weight)`
- Handles cold start (new instructors with few reviews)

#### Distance Score (15%)
- Decay curve based on distance from search location
- 0 miles = 1.0, 5 miles = 0.5, 10+ miles = 0.1

#### Price Score (10%)
- If max_price specified: higher score if price ≤ max
- Normalized to 0-1 range

#### Freshness Score (10%)
- Based on last activity (lessons, reviews, profile updates)
- Recent activity = higher score

#### Completeness Score (5%)
- Profile photo, bio, services listed, availability set
- More complete = higher score

### Boost Factors

#### Audience Boost
```
If query.audience = "kids" AND instructor teaches kids:
  +0.05 boost

If instructor has "Great with Kids" badge:
  +0.03 additional boost
```

#### Skill Level Boost
```
If query.skill_level = "beginner" AND instructor teaches beginners:
  +0.03 boost
```

### Ranking Example

```
Query: "piano for kids in ues"

Candidate A (Sarah C.):
  relevance: 0.92 (exact "Piano" match)
  quality: 0.74 (3.7 stars, 3 reviews)
  distance: 1.0 (0.0 mi - in UES)
  price: 0.8 ($120/hr)
  freshness: 0.9 (active last week)
  completeness: 0.95 (full profile)
  audience_boost: 0.05 (teaches kids)

  Score = 0.35×0.92 + 0.25×0.74 + 0.15×1.0 + 0.10×0.8 + 0.10×0.9 + 0.05×0.95 + 0.05
        = 0.322 + 0.185 + 0.15 + 0.08 + 0.09 + 0.048 + 0.05
        = 0.925

Candidate B (Michael R.):
  relevance: 0.88 (also teaches Piano)
  quality: 1.0 (5.0 stars, 3 reviews)
  distance: 0.4 (2.1 mi - outside UES)
  price: 0.9 ($85/hr - cheaper)
  freshness: 0.85
  completeness: 0.9
  audience_boost: 0.05

  Score = 0.35×0.88 + 0.25×1.0 + 0.15×0.4 + 0.10×0.9 + 0.10×0.85 + 0.05×0.9 + 0.05
        = 0.308 + 0.25 + 0.06 + 0.09 + 0.085 + 0.045 + 0.05
        = 0.888

Result: Sarah C. (0.925) ranks above Michael R. (0.888)
        Even though Michael has better ratings, Sarah's location match wins.
```

---

## 6. Caching

### 4-Layer Cache System

| Layer | Key Pattern | TTL | Purpose |
|-------|-------------|-----|---------|
| Response | `search:v{N}:{hash}` | 5 min | Skip entire pipeline |
| Parsed Query | `parsed:{hash}` | 1 hour | Skip parsing |
| Embedding | `embed:{model}:{hash}` | 24 hours | Skip OpenAI API |
| Location | `geo:{location}` | 7 days | Skip geocoding |

### Cache Key Generation

```python
# Response cache key includes all parameters
cache_key = f"search:v1:{query}:{lat}:{lng}:{limit}"

# Hash for long keys
cache_key = f"search:v1:{sha256(normalized_query)}"
```

### Version-Based Invalidation

When search logic changes, increment version to invalidate all cached responses:

```python
CACHE_VERSION = 2  # Bump this to invalidate

cache_key = f"search:v{CACHE_VERSION}:{hash}"
```

### Degraded Response Caching

Even degraded responses (embedding timeout, etc.) are cached with short TTL:

```python
if degraded:
    ttl = 30  # 30 seconds - don't serve stale fallback for long
else:
    ttl = 300  # 5 minutes for normal responses
```

---

## 7. Self-Learning

### Learning Flow

```
1. User searches "piano near museum mile"
                    │
2. "museum mile" fails Tiers 1-3
                    │
3. Tier 4/5 resolves to "Upper East Side"
   (or fails → tracked as unresolved)
                    │
4. User clicks instructor in "Carnegie Hill"
                    │
5. Click recorded: ("museum mile" → "Carnegie Hill")
                    │
6. After 5+ similar clicks (70%+ to same region)...
                    │
7. Daily Celery task learns alias:
   "museum mile" → "Upper East Side-Carnegie Hill"
                    │
8. Next search for "museum mile" → Tier 2 instant match!
```

### Unresolved Query Tracking

```sql
-- Tracked in unresolved_location_queries
INSERT INTO unresolved_location_queries (
    query_normalized,   -- "madeupplace"
    search_count,       -- How many times searched
    click_count,        -- How many clicks recorded
    click_region_counts -- {"Carnegie Hill": 7, "Midtown": 2}
)
```

### Learning Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| Min clicks | 3 | Need enough data |
| Min confidence | 70% | Most clicks to same region |
| Min occurrences | 5 | Query must be common |
| Auto-approve | 90%+ | Very clear pattern |

### Admin Review

Low-confidence learned aliases go to admin review:

```
/admin/location-learning

Pending Aliases:
| Alias        | → Region           | Confidence | Actions          |
|--------------|--------------------| -----------|------------------|
| "theater st" | Midtown-Times Sq   | 75%        | [Approve][Reject]|
```

---

## 8. Performance Characteristics

### Latency Breakdown

| Stage | Typical | With Cache |
|-------|---------|------------|
| Cache check | 1-2ms | - |
| Parsing | 5-10ms | - |
| Location resolution | 10-100ms | - |
| Embedding generation | 100-400ms | Cached: 2ms |
| Candidate retrieval | 20-50ms | - |
| Filtering | 10-30ms | - |
| Ranking | 5-15ms | - |
| **Total (cold)** | **200-600ms** | - |
| **Total (cached)** | **2-5ms** | ✅ |

### Degradation Modes

The system gracefully degrades when components fail:

| Failure | Fallback | Impact |
|---------|----------|--------|
| Embedding timeout | Text-only retrieval | Less semantic matching |
| OpenAI API down | Cached embeddings + text | Slightly less relevant |
| Redis down | No caching | Higher latency |
| Location resolution fails | Show all results | No geographic filtering |

---

## 9. Complete Query Examples

### Example A: Simple Query
```
Query: "piano lessons"

Parsing:
  service_query: "piano lessons"
  (no other constraints)

Location: Not specified → no filtering
Retrieval: 30 candidates matching "piano"
Filtering: None applied
Ranking: By relevance + quality
Results: 20 (limit)
Cache: Stored for 5 minutes
```

### Example B: Complex Query
```
Query: "cheap guitar lessons for my 10 year old in brooklyn next tuesday evening"

Parsing:
  service_query: "guitar lessons"
  location: "brooklyn"
  date: 2025-12-23 (next tuesday)
  time_after: "17:00"
  time_before: "21:00"
  max_price: 60 (cheap)
  audience: "kids"

Location Resolution:
  "brooklyn" → Tier 2 (borough alias) → All Brooklyn neighborhoods

Retrieval: 25 guitar instructors
Filtering:
  Price ≤$60: 18
  Location (Brooklyn): 12
  Audience (kids): 8
  Availability (Tue evening): 3

Ranking: By combined score
Results: 3 instructors
Message: None (no relaxation needed)
```

### Example C: Typo + Ambiguous Location
```
Query: "paino in ues tomorrow"

Parsing:
  service_query: "paino" → corrected to "piano" via pg_trgm
  location: "ues"
  date: 2025-12-16 (tomorrow)

Location Resolution:
  "ues" → Tier 2 (alias) → AMBIGUOUS
  Candidates: [Carnegie Hill, Lenox Hill, Yorkville]

Display: "Upper East Side (Carnegie Hill, Lenox Hill-Roosevelt Island, Yorkville)"

Retrieval: 30 candidates
Filtering:
  Location (3 UES regions): 8
  Availability (tomorrow): 2

Results: 2 instructors
Distance: Calculated as minimum across all 3 candidate regions
```

### Example D: Unresolvable Location with Relaxation
```
Query: "violin in lic monday 9am"

Parsing:
  service_query: "violin"
  location: "lic"
  date: 2025-12-22 (monday)
  time_after: "09:00"
  time_before: "10:00"

Location Resolution:
  "lic" → Tier 2 (alias) → "Long Island City-Hunters Point"

Retrieval: 15 violin instructors
Filtering:
  Location (LIC): 0 ← No instructors in LIC!

Relaxation:
  Relax time → still 0
  Relax date → still 0
  Relax location → 5 instructors from nearby areas

Results: 5 instructors
Message: "Showing 5 results from nearby areas. No instructors found in
          Long Island City-Hunters Point. No availability on Monday, Dec 22.
          Relaxed: time, date, location."
```

### Example E: Semantic Location Match
```
Query: "piano near times square"

Parsing:
  service_query: "piano"
  location: "times square"

Location Resolution:
  Tier 1: ❌ "times square" not exact region name
  Tier 2: ❌ No alias
  Tier 2.5: ❌ No substring
  Tier 3: ❌ Fuzzy 0.35 < 0.4
  Tier 4: ✅ Embedding similarity 0.86
    "times square" ≈ "Midtown-Times Square"

Results: Instructors in Midtown-Times Square area
```

### Example F: Self-Learning Trigger
```
Query: "piano near lincoln center"

Location Resolution:
  Tier 1-5: All fail (or resolve incorrectly)
  location_not_found: true

Tracking:
  → Saved to unresolved_location_queries

User Behavior:
  → User clicks instructor in "Lincoln Square"
  → Click recorded: "lincoln center" → "Lincoln Square"

After 5 similar clicks:
  → Celery task creates alias
  → "lincoln center" → "Lincoln Square" (status: active)

Next Search:
  → Tier 2 instant match!
```

---

## 10. Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | - | Required for embeddings |
| `OPENAI_EMBEDDING_MODEL` | text-embedding-3-small | Embedding model |
| `OPENAI_EMBEDDING_TIMEOUT_MS` | 2000 | Embedding timeout |
| `OPENAI_PARSING_MODEL` | gpt-5-nano | LLM for Tier 5 |
| `EMBEDDING_SIMILARITY_THRESHOLD` | 0.82 | Tier 4 threshold |
| `FUZZY_SIMILARITY_THRESHOLD` | 0.4 | Tier 3 threshold |
| `MIN_FUZZY_FOR_EMBEDDING` | 0.25 | Guard for Tier 4 |
| `SEARCH_CACHE_TTL` | 300 | Response cache TTL (seconds) |
| `DEGRADED_CACHE_TTL` | 30 | Degraded response TTL |

### Tuning Tips

| Scenario | Adjustment |
|----------|------------|
| Too many false positives | Raise EMBEDDING_SIMILARITY_THRESHOLD |
| Missing good matches | Lower thresholds slightly |
| Slow searches | Check embedding timeout, enable caching |
| High OpenAI costs | Use cached embeddings, mock for tests |

---

## Summary

InstaInstru's NL Search transforms natural language into structured queries through:

1. **Smart Parsing** - Extracts 8+ constraint types from free text
2. **5-Tier Location Resolution** - From exact match to AI interpretation
3. **Hybrid Retrieval** - Semantic + text search with guardrails
4. **Intelligent Filtering** - With progressive relaxation
5. **Multi-Signal Ranking** - Balances relevance, quality, distance, price
6. **4-Layer Caching** - Sub-5ms responses for repeated queries
7. **Self-Learning** - Improves from user behavior

The result: Users can search naturally and find the right instructor quickly.

```
"cheap piano for my kid in brooklyn tomorrow morning"
     ↓
  2 perfect matches in 250ms
```
