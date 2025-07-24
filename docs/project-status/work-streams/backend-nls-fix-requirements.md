# Backend NLS Algorithm Fix Requirements
*Created: July 24, 2025 - Session v75*
*Priority: CRITICAL - Work Stream #15*

## Status: 🔴 CRITICAL PRIORITY #1 - Service-First Search Excellence

## Problem Statement

The natural language search algorithm is matching instructors at the category level instead of the specific service level. When a user searches for a specific service with constraints (e.g., "piano under $80"), the system returns ALL instructors in that category who meet the constraints, not just instructors who teach the specific service.

This completely undermines the service-first paradigm that the platform is built on and affects the precision of search results that users expect.

## Current vs Expected Behavior

### Example Query: "piano under $80"

**Current Results** (WRONG):
```
1. Sarah Chen - Piano ($75) ✅
2. Mike Rodriguez - Drums ($60) ❌
3. Alex Johnson - Drums ($65) ❌
4. Lisa Wang - Bass Guitar ($70) ❌
5. Emily Davis - Music Theory ($55) ❓
6. James Wilson - Ukulele ($45) ❌
```

**Expected Results** (CORRECT):
```
1. Sarah Chen - Piano ($75) ✅
2. [Any other piano instructors under $80]
```

### Why This Matters

1. **User Trust**: Users searching for "piano lessons" don't want to see drums instructors
2. **Service-First Vision**: The entire UI/UX is built around selecting services first
3. **Conversion Impact**: Users abandon searches when seeing irrelevant results
4. **Instructor Fairness**: Popular instruments crowd out specific searches

## Root Cause Analysis

The backend algorithm appears to be:

```python
# CURRENT (Incorrect) Logic:
1. Parse query → Extract service: "piano", constraint: "under $80"
2. Find category for service → "Music"
3. Find ALL instructors in Music category
4. Filter by constraint → price < $80
5. Return results (includes drums, guitar, etc.)

# SHOULD BE:
1. Parse query → Extract service: "piano", constraint: "under $80"
2. Find instructors who teach SPECIFICALLY "piano"
3. Filter by constraint → price < $80
4. Return ONLY piano instructors
```

## Technical Requirements

### Fix Implementation
The algorithm must enforce AND logic at the service level:
- Match specific service(s) from query
- Apply constraints to ONLY those service matches
- Do NOT expand to category siblings

### Key Files to Update (Likely)
- Natural language search service/controller
- Service matching algorithm
- Instructor filtering logic
- Query builder combining service + constraints
- Vector similarity search scope

### Performance Considerations
- Maintain <50ms response time
- Use existing embeddings efficiently
- Don't break category browsing (which works correctly)

## Test Cases for Verification

After implementing the fix, ALL of these should pass:

### Service-Specific Queries
1. "piano under $80" → ONLY piano instructors under $80
2. "spanish lessons tomorrow" → ONLY Spanish instructors available tomorrow
3. "yoga classes near me" → ONLY yoga instructors in the area
4. "SAT prep this weekend" → ONLY SAT tutors available this weekend

### Edge Cases
1. "music lessons under $50" → This SHOULD return multiple music types
2. "lessons under $30" → This is category-agnostic, return all under $30
3. "piano or guitar under $60" → Return ONLY piano and guitar instructors

### Verification Against Browse Path
The natural language results should match:
- Click "Piano" service → Get 5 instructors
- Search "piano" → Same 5 instructors
- Search "piano under $80" → Subset of those 5

## Implementation Approach

### Phase 1: Investigation (2-3 hours)
1. Trace the current query flow
2. Identify where category expansion happens
3. Understand the vector search scope

### Phase 2: Implementation (4-6 hours)
1. Modify service matching to be strict
2. Update query builder logic
3. Ensure constraints apply post-service-match

### Phase 3: Testing (2-3 hours)
1. Run all test cases above
2. Verify performance maintained
3. Ensure category browse still works

### Phase 4: Deployment (1 hour)
1. Deploy fix
2. Monitor search queries
3. Verify in production

## Success Metrics

1. **Accuracy**: Service-specific queries return ONLY that service
2. **Performance**: Maintain <50ms response time
3. **No Regressions**: Category browsing still works perfectly
4. **User Satisfaction**: Search results match user intent

## Timeline

**Total Effort**: 1-2 days
- Day 1: Investigation and implementation
- Day 2: Testing and deployment

## Dependencies

- No dependencies on other work
- Frontend is ready and waiting for this fix
- Analytics will immediately show improved search quality

## Risk Mitigation

1. **Test Thoroughly**: All test cases must pass
2. **Performance Testing**: Ensure no degradation
3. **Rollback Plan**: Be ready to revert if issues
4. **Monitor Post-Deploy**: Watch search metrics closely

## 🎯 Session v75 Context

### Platform State
- **Backend**: 100% architecturally complete ✅
- **Frontend**: Service-first transformation complete (270+ services) ✅
- **Analytics**: Automated in production ✅
- **Platform Completion**: ~82% ready
- **Critical Blocker**: NLS algorithm precision (this fix)

### Why This Is Priority #1
1. **User Experience**: Search is primary user interaction point
2. **Service-First Vision**: Entire platform architecture built around precise service matching
3. **Platform Excellence**: Quality search required for megawatt energy allocation
4. **Ready Infrastructure**: Frontend service-first ready, waiting for backend precision

### Expected Impact
- **Platform Readiness**: ~82% → ~85% with excellent search
- **User Satisfaction**: Dramatic improvement in search relevance
- **Platform Quality**: Core user experience becomes excellent
- **Energy Allocation**: Quality platform proves megawatt worthiness

---

**This is THE critical blocker for service-first search excellence. Once fixed, the platform achieves its core vision of helping users find precisely WHAT they want to learn with exceptional search quality! ⚡🚀**
