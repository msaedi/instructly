# Launch State and Capabilities

**Status:** Approved design, pre-implementation
**Owners:** Backend, Frontend, Platform Admin
**Last updated:** 2026-04-25

---

## TL;DR

iNSTAiNSTRU's launch posture is modeled as **two independent access axes** — one for instructors, one for students — with instructor states `closed`, `invite_only`, `open` and student states `closed`, `referral_only`, `open`. Specific capabilities (can sign up, can refer, can browse directory, etc.) derive deterministically from these two axes. State-level overrides allow time-bounded exceptions for events. Capabilities are enforced at three layers: backend route, backend service, and frontend UI.

This document is the contract. New features that depend on launch posture must consult `LaunchState` and `Capabilities`. Do not introduce new global flags for launch behavior.

---

## Why this exists

Before this model, iNSTAiNSTRU had three drifting boolean flags:

- `BetaSettings.beta_phase` — DB-stored phase string, admin-mutable
- `BetaSettings.allow_signup_without_invite` — independent boolean, admin-mutable
- `PlatformConfig.public_platform.student_launch_enabled` — JSON config field, admin-mutable

These were independently consumed:

- The proxy honored `allow_signup_without_invite` for routing
- The backend `invite_required_for_registration(role, phase)` ignored it
- The frontend derived phase from hostname, not from the backend
- `student_launch_enabled` only controlled one frontend button, not actual student access

Drift caused real bugs:

- Founder emails could be burned by the student signup link on the instructor signup page (Issue #2)
- Referrals page rendered fully on the dashboard but referees could not complete signup (Issue #16)
- Founding slot accounting was accidentally recovered by hard-deleting instructor profiles, but the consumed invite was never freed (Issue #23)

This document defines a single source of truth that replaces all three flags and prevents this class of bug going forward.

---

## The model

### Two access axes

```python
class InstructorAccess(str, Enum):
    CLOSED = "closed"           # No instructor signup (internal only)
    INVITE_ONLY = "invite_only" # Founding cohort or controlled rollout, requires invite code
    OPEN = "open"               # Public instructor signup, no invite required

class StudentAccess(str, Enum):
    CLOSED = "closed"           # No student signup, student UI hidden
    REFERRAL_ONLY = "referral_only" # Students sign up via instructor referral only
    OPEN = "open"               # Public student signup
```

Three states per axis, nine total combinations. Each combination is a valid platform posture. The most common will be:

| Instructor | Student | Meaning |
|------------|---------|---------|
| `invite_only` | `closed` | Founding round (current state at time of writing) |
| `invite_only` | `open` | Students public, instructors still vetted/cost-controlled |
| `open` | `open` | Public GA |

Other combinations are valid but less common. The model does not constrain combinations; product decisions choose which states to inhabit and when to advance.

### LaunchState — singleton row

```python
class LaunchState(Base):
    """The current platform-level launch posture. Singleton row (id=1)."""
    id: Mapped[int]                                  # always 1
    instructor_access: Mapped[InstructorAccess]
    student_access: Mapped[StudentAccess]
    overrides: Mapped[dict]                          # JSONB, see Overrides below
    updated_at: Mapped[datetime]
    updated_by: Mapped[str]                          # admin email for audit
    notes: Mapped[Optional[str]]                     # free-text reason for last change
```

DB-level constraints:
- Primary key forces single row (`id = 1`)
- Both axis columns have CHECK constraints listing allowed enum values
- Updates trigger a row in `launch_state_audit` for full history

This singleton replaces:
- `BetaSettings.beta_phase` → `LaunchState.instructor_access` + `LaunchState.student_access`
- `BetaSettings.allow_signup_without_invite` → derived from `instructor_access != INVITE_ONLY`, or via override
- `BetaSettings.beta_disabled` → `instructor_access == CLOSED && student_access == CLOSED`
- `PlatformConfig.public_platform.student_launch_enabled` → derived from `student_access != CLOSED`

The old fields are removed in the migration. There is no compatibility shim.

### Capabilities — derived, deterministic, immutable

```python
@dataclass(frozen=True)
class Capabilities:
    # Instructor side
    can_signup_as_instructor: bool
    instructor_signup_requires_invite: bool
    can_refer_instructors: bool

    # Student side
    can_signup_as_student: bool
    student_signup_requires_referral: bool
    can_refer_students: bool
    can_browse_public_directory: bool
    can_view_student_marketing: bool

    # Telemetry
    instructor_access: InstructorAccess
    student_access: StudentAccess
    overridden: frozenset[str]   # which capability names were overridden
```

`Capabilities` is computed by `derive_capabilities(state: LaunchState) -> Capabilities`. The function is pure: same inputs always produce the same output. It runs identically in backend Python and frontend TS (the TS port is generated or hand-maintained alongside the Python source).

Derivation logic per capability:

| Capability | Source |
|-----------|--------|
| `can_signup_as_instructor` | `instructor_access != CLOSED` |
| `instructor_signup_requires_invite` | `instructor_access == INVITE_ONLY` |
| `can_refer_instructors` | `instructor_access != CLOSED` |
| `can_signup_as_student` | `student_access != CLOSED` |
| `student_signup_requires_referral` | `student_access == REFERRAL_ONLY` |
| `can_refer_students` | `student_access != CLOSED` |
| `can_browse_public_directory` | `student_access != CLOSED` |
| `can_view_student_marketing` | `student_access != CLOSED` |

Each capability derives from one axis. There are no cross-axis derivations today. If one is needed in the future (e.g., "can_view_directory_as_instructor" depending on both axes), document it explicitly here.

Overrides are applied on top of the base derivation. See next section.

### Overrides — state-level, time-bounded, audited

Overrides allow temporary exceptions to the derived capabilities. They exist for moments when the platform needs to deviate without changing the underlying launch state. Examples:

- Recruiting event next week needs student signup temporarily open
- Investigation in progress, instructor referrals temporarily disabled
- Demo for an investor needs a single capability shown without flipping the launch state

Override schema:

```python
# overrides JSONB structure
{
  "<capability_name>": {
    "value": <bool>,
    "expires_at": "<ISO 8601 UTC>",     # REQUIRED, max 30 days from set_at
    "set_at": "<ISO 8601 UTC>",
    "set_by": "<admin email>",
    "reason": "<free text, min 10 chars>"
  }
}
```

Constraints (enforced at the admin endpoint):

- `expires_at` is required and cannot exceed 30 days from `set_at`
- `reason` is required, minimum 10 characters
- Only capabilities whose name appears in the `Capabilities` dataclass can be overridden
- Renewal creates a new override entry replacing the old one; both events are audit-logged
- Expired overrides are automatically purged by a daily Celery task

Overrides are platform-level. If a per-user exception is needed (e.g., a specific user can sign up early), use the existing `BetaInvite` mechanism — that is a separate axis entirely.

---

## Defense in depth

Every capability is enforced at three layers. UI is a hint, the route is a gate, the service is law.

### Layer 1: Frontend UI

```typescript
const { capabilities } = useLaunch();
if (!capabilities.canSignupAsStudent) return null;
```

UI hiding is the most visible layer but the least authoritative. Users who bypass the UI (direct URL navigation, API calls, etc.) must still be rejected by the backend.

### Layer 2: Backend route

```python
@router.post(
    "/register",
    dependencies=[Depends(require_capability_for_registration_role)],
)
def register_user(...):
    ...
```

Route-level dependencies guard the entrypoint. New endpoints that touch launch-controlled functionality must include the appropriate dependency.

### Layer 3: Backend service

```python
class AuthService:
    def register_user(self, role: str, ...):
        caps = self.launch_service.current_capabilities()
        if role == "student" and not caps.can_signup_as_student:
            raise CapabilityDisabledException("can_signup_as_student")
        if role == "instructor" and not caps.can_signup_as_instructor:
            raise CapabilityDisabledException("can_signup_as_instructor")
        if invite_code:
            invite = self.invite_repo.get_by_code(invite_code)
            if invite.role != role:
                raise CapabilityDisabledException("invite_role_mismatch")
        ...
```

Service-level checks defend against bypassed routes (internal services, future API surfaces, scripts). Even if Layer 2 is missing on a route, Layer 3 catches the violation.

The role-mismatch check above closes a real gap: invite codes today have a `role` column but `mark_used` does not validate it against the registering user's role. The capability layer's defense in depth fixes this.

---

## Account lifecycle (separate but parallel concern)

Account state is also an enum, modeled separately from launch state. They are orthogonal: launch state controls what's possible at the platform level, account status controls what's possible for an individual user.

```python
class AccountStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification" # email not yet confirmed
    ACTIVE = "active"
    SUSPENDED = "suspended"     # paused, reversible (self or admin)
    DEACTIVATED = "deactivated" # user-initiated exit, admin can revert
    DELETED = "deleted"         # PII wiped, audit row retained
    PURGED = "purged"           # row removed (legal/compliance only)

class User(Base):
    account_status: Mapped[AccountStatus]
    status_changed_at: Mapped[datetime]
    deleted_at: Mapped[Optional[datetime]]
    purged_at: Mapped[Optional[datetime]]
```

Valid transitions:

- `PENDING_VERIFICATION → ACTIVE` (email verified)
- `ACTIVE → SUSPENDED` (self-pause, instructor stays logged in, existing bookings honored)
- `SUSPENDED → ACTIVE` (resume)
- `ACTIVE → DEACTIVATED` (user-initiated, blocks future bookings, revokes tokens)
- `DEACTIVATED → ACTIVE` (admin-initiated reactivation)
- `ACTIVE | SUSPENDED | DEACTIVATED → DELETED` (data anonymization, audit row kept)
- `DELETED → PURGED` (legal request, post-retention period only)

Transitions are validated at the service layer. `AccountStatus` and the related transition rules are documented separately in `docs/architecture/account-lifecycle.md` (to be created when this design ships).

---

## Founding slots

Founding instructor slots are a separate concern from launch state. They are an internal accounting construct: how many of a fixed cap (currently 100) have been allocated, claimed, or are still open.

```python
class FoundingSlotState(str, Enum):
    OPEN = "open"          # slot available, no invite issued
    ALLOCATED = "allocated" # invite issued for this slot, not yet claimed
    CLAIMED = "claimed"     # instructor signed up, slot is permanently used

class FoundingSlot(Base):
    id: Mapped[ULID]
    state: Mapped[FoundingSlotState]
    invite_id: Mapped[Optional[ULID]]      # FK when ALLOCATED
    user_id: Mapped[Optional[ULID]]         # FK when CLAIMED
    claimed_at: Mapped[Optional[datetime]]
    history: Mapped[list]                   # audit trail of state transitions
```

Lifecycle:

```
OPEN
  → ALLOCATED  (invite issued)
ALLOCATED
  → CLAIMED   (instructor signs up)
  → OPEN      (invite revoked before claim, slot returns to pool)
CLAIMED
  [terminal under normal operation]
```

**No grace period.** Once `CLAIMED`, the slot is permanently consumed. If a founder deletes their account immediately after claiming, the slot is gone. This is acceptable because:

- Founding slots are an internal cap, not a contract written in stone. We can issue more if needed.
- Adding a grace period creates scheduled jobs to expire grace windows, complicates the state model, and doesn't defend against any real attack we care about.
- Recovery via admin action is always possible (an admin can manually transition a `CLAIMED` slot back to `OPEN` if a forfeiture is genuine and documented).

Cap enforcement is a single query:

```sql
SELECT count(*) FROM founding_slots
WHERE state IN ('allocated', 'claimed')
```

To raise the cap, insert more `OPEN` rows. To lower the cap, archive `OPEN` rows.

---

## Header propagation and SSR

The frontend must read launch state from the backend, not from hostname. The current hostname-based derivation (in `frontend/lib/beta-config.ts`) is removed.

Backend response middleware emits two headers on every response:

```
x-instructor-access: invite_only
x-student-access: closed
x-launch-overrides-hash: a4b9c2
```

The `overrides-hash` is `sha256(canonical_json(non_expired_overrides))[:8]`. It exists for cache invalidation: if the hash changes, the frontend refetches the full capability snapshot from `/api/v1/config/capabilities`. If unchanged, the cached snapshot is reused.

Frontend SSR layout reads the headers via `getLaunchStateFromHeaders(await headers())`, runs the same `deriveCapabilities()` logic ported to TS, and passes the result to `<LaunchProvider>`. Client components consume via `useLaunch()`:

```typescript
const { capabilities, instructorAccess, studentAccess } = useLaunch();
```

Hostname is no longer used for launch state. It still serves to identify the deployment environment (`beta.instainstru.com` vs `preview.instainstru.com` vs `instainstru.com`) for purposes orthogonal to launch state.

---

## How to extend this model

### Adding a new capability

1. Add the field to the `Capabilities` dataclass in `backend/app/core/capabilities.py`
2. Add the derivation rule in `_derive_from_axes` (or `_derive_from_overrides` if it's override-only)
3. Mirror the change in the TS `Capabilities` type and `deriveCapabilities` function
4. Add to the table in this document under "Derivation logic per capability"
5. Add backend route dependency `require_capability("<new_capability>")` to relevant endpoints
6. Add service-layer check at the relevant entrypoints
7. Add frontend `useLaunch().capabilities.<newCapability>` consumption to relevant components
8. Add tests for both axes that exercise the capability

### Adding a new override

Overrides are admin-set at runtime, not code changes. To set one:

```
POST /api/v1/admin/launch-state/overrides
{
  "capability": "can_signup_as_student",
  "value": true,
  "expires_at": "2026-05-15T23:59:59Z",
  "reason": "Recruiting event 2026-05-10"
}
```

This is logged to `launch_state_audit`. Capabilities re-derive on the next request (or push via WebSocket if implemented later).

### Advancing launch state

```
PUT /api/v1/admin/launch-state
{
  "instructor_access": "open",
  "student_access": "open",
  "notes": "Public launch 2026-Q3"
}
```

This is the only way to change the launch state outside of overrides. The change is audited. All capabilities re-derive immediately. Active overrides remain active until they expire.

### Removing the model (don't)

If you find yourself wanting to add a new global boolean flag for launch behavior, stop. That is the failure mode this model exists to prevent. Either:
- It belongs as an axis state (rare, requires this document to be updated)
- It belongs as a capability derived from axes (common)
- It belongs as a per-user permission (use `PermissionService` and `BetaInvite`, separate system)

---

## Migration from the old model

Pre-launch, no real production users to protect. The migration is a single Alembic migration edited in place per project convention (no new migration files for pre-launch schema changes).

Steps:

1. Create `LaunchState` table, seed `(id=1, instructor_access='invite_only', student_access='closed', overrides={})`
2. Create `FoundingSlot` table, seed 100 OPEN rows; migrate any already-issued founding invites to ALLOCATED state with `invite_id` populated; migrate already-claimed founding instructors to CLAIMED state with `user_id` populated
3. Add `AccountStatus` enum constraint to `users.account_status`; migrate existing `is_active` + `account_status` string into the enum (most rows are ACTIVE; deactivated/deleted users transition appropriately)
4. Add `users.deleted_at` and `users.purged_at` columns
5. Add CHECK constraint on `BetaInvite.role` requiring it be set
6. Drop `BetaSettings.allow_signup_without_invite`
7. Drop `PlatformConfig.public_platform.student_launch_enabled`
8. (Optional, defer) Drop `BetaSettings` table entirely after confirming nothing else reads from it

Frontend migration:

1. Replace `getBetaConfigFromHeaders` with `getLaunchStateFromHeaders`
2. Replace `BetaProvider`/`useBeta` with `LaunchProvider`/`useLaunch`
3. Update all components currently reading `betaConfig.phase` or `betaConfig.site` to read `useLaunch().capabilities.<...>` instead
4. Remove hostname-based phase derivation in `frontend/lib/beta-config.ts` (keep hostname → site/environment derivation, that's still useful)

Backend migration:

1. Replace `invite_required_for_registration(role, phase)` with `require_capability_for_registration_role` dependency
2. Add capability checks in `AuthService.register_user` (defense in depth)
3. Add `invite.role == role` check at every invite consumption site (`mark_used`, `BetaService.consume_and_grant`, `register_user`)
4. Replace `student_launch_enabled` reads with `capabilities.can_signup_as_student`

This is a substantial migration but a single coherent PR. Tests will cover every capability × axis combination explicitly (3 × 3 = 9 axis combinations × N capabilities = bounded matrix).

---

## Open questions

These are not blockers but are flagged for product decision before launch:

1. **Override notification policy.** Should admins receive an email warning 24 hours before a production-affecting override expires? Currently undefined. Recommendation: yes, for any override on a capability prefixed `can_signup_*`.

2. **Override audit retention.** Active and recently-expired overrides are visible in the admin UI. How long do we keep audit history for removed/expired overrides? Recommendation: 1 year, then archive to S3.

3. **Beta access grants vs capabilities.** Existing `BetaAccess` grants give specific users elevated access. They predate this model. Should they be folded into the capability layer (e.g., as per-user override grants), or remain a separate per-user mechanism? Recommendation: keep separate. Capabilities are platform-level; per-user is a different problem.

4. **Founding cap adjustments.** If the cap needs to change post-launch (currently 100), do we increase it via direct DB inserts of OPEN rows, or a dedicated admin endpoint? Recommendation: dedicated endpoint, audited.

---

## Glossary

- **LaunchState**: The singleton row in the `launch_state` table representing the current platform posture.
- **Axis**: One of the two independent dimensions (`InstructorAccess`, `StudentAccess`) that comprise launch state.
- **Capability**: A derived boolean expressing what's allowed in the current launch state. Always computed, never stored.
- **Override**: A time-bounded, platform-level exception to a derived capability.
- **Defense in depth**: Enforcement of a capability at all three layers (UI, route, service) so that bypass at any one layer does not grant access.
- **Founding slot**: An internal accounting unit for the founding instructor cohort, separate from launch state.

---

## References

- Issue #2: Student signup link burns founder emails (closed by capability + UI gate)
- Issue #16: Referrals page visible but referees cannot complete signup (closed by capability)
- Issue #23: Account deletion + founding slot recovery (closed by lifecycle + ledger)
- Investigation report: phase/capability architecture (April 2026)
- CARL decision log: `BACKEND` domain entries on launch policy
