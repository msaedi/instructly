# Cache Key Inventory

| Cache Key Pattern | Set Location | TTL | Data Cached | Should Invalidate When |
|---|---|---|---|---|
| `notif:{user_id}:{YYYYMMDD}` | `backend/app/notifications/policy.py:68` | 36h default (ttl_hours * 3600) | Per-user daily notification count | Daily rollover (TTL) or manual reset |
| `login:minute:{email}` | `backend/app/core/login_protection.py:232` | 60s | Login attempts per minute | TTL expiry or reset on success |
| `login:hour:{email}` | `backend/app/core/login_protection.py:234` | 3600s | Login attempts per hour | TTL expiry or reset on success |
| `login:failures:{email}` | `backend/app/core/login_protection.py:351` | 3600s | Failed login counter | Reset on successful login |
| `login:lockout:{email}` | `backend/app/core/login_protection.py:356` | lockout_seconds (threshold-based) | Lockout marker ("1") | Reset on successful login or TTL expiry |
| `auth_user:{email}` | `backend/app/core/auth_cache.py:87` | 1800s | User auth payload (roles, permissions, profile flags) | User role/profile/beta/access changes |
| `permissions:{user_id}` | `backend/app/services/permission_cache.py:60` | 300s | User permissions set | Role/permission changes |
| `sse_token:{token}` | `backend/app/routes/v1/sse.py:42` | 30s | User id for SSE token | TTL expiry only |
| `profile_pic_url:{user_id}:{variant}:v{version}` | `backend/app/services/personal_asset_service.py:199` | 2700s | Presigned profile picture URL + expiry | Profile picture update or version bump |
| `favorites:{student_id}:{instructor_id}` | `backend/app/services/favorites_service.py:184` | 300s | Favorite status ("1"/"0") | Favorite add/remove |
| `coverage:bulk:{comma_joined_instructor_ids}` | `backend/app/services/address_service.py:397` | tier=hot (300s) | GeoJSON coverage polygons | Service area changes |
| `neighborhoods:{region_type}:{borough|all}:{limit}:{offset}` | `backend/app/services/address_service.py:436` | tier=warm (3600s) | Neighborhood list | Region data changes |
| `avail:week:{instructor_id}:{week_start}` | `backend/app/services/availability_service.py:993` | tier=hot (300s) or warm (3600s) | Week availability map (bitmap-derived) | Availability changes, booking changes |
| `avail:week:{instructor_id}:{week_start}:with_slots` | `backend/app/services/availability_service.py:992` | tier=hot (300s) or warm (3600s) | Week availability payload (map + metadata) | Availability changes, booking changes |
| `avail:range:{instructor_id}:{start}:{end}` | `backend/app/services/cache_service.py:760` | tier=hot (300s) or warm (3600s) | Availability for date range | Availability changes, booking changes |
| `avail:weekly:{instructor_id}` | `backend/app/services/cache_service.py:784` | tier=hot (300s) | Weekly availability pattern | Availability changes |
| `con:{instructor_id}:{date}:{hash}` | `backend/app/services/cache_service.py:881` | tier=hot (300s) | Booking conflict check results | Availability or booking changes |
| `public_availability:{instructor_id}:{start}:{end}:{detail_level}` | `backend/app/routes/v1/public.py:453` | settings.public_availability_cache_ttl | Public availability response for students | Availability changes, booking changes, blackout changes |
| `instructor:public:{instructor_id}` | `backend/app/services/instructor_service.py:391` | 300s | Public instructor profile | Profile/service/photo changes |
| `catalog:services:{category_slug|all}` | `backend/app/services/instructor_service.py:1014` | 300s | Catalog services list (per category) | Catalog/service updates |
| `categories:all` | `backend/app/services/instructor_service.py:1047` | 3600s | Service categories | Category updates |
| `catalog:top-services:{limit}` | `backend/app/services/instructor_service.py:1431` | 3600s | Top services per category | Analytics or catalog changes |
| `catalog:all-services-with-instructors` | `backend/app/services/instructor_service.py:1553` | 300s | All services with instructor counts | Catalog/services/analytics changes |
| `catalog:kids-available` | `backend/app/services/instructor_service.py:1575` | 300s | Services available for kids | Catalog/services changes |
| `booking_stats:instructor:{instructor_id}` | `backend/app/services/booking_service.py:1265` | tier=hot (300s) | Instructor booking stats | Booking create/update/cancel/no-show/complete |
| `ratings:{version}:instructor:{instructor_id}` | `backend/app/services/review_service.py:428` | 300s | Instructor ratings summary | Review create/update/delete |
| `ratings:search:{version}:{instructor_id}:{service_id|all}` | `backend/app/services/review_service.py:525` | 300s | Search rating summary | Review create/update/delete |
| `template:context:common` | `backend/app/services/template_service.py:198` | 3600s | Common email template context | Template/settings changes |
| `template:exists:{template_name}` | `backend/app/services/template_service.py:364` | 86400s | Template exists boolean | Template changes |
| `geo:ip:{hash}` | `backend/app/services/geolocation_service.py:102` | 86400s | IP geolocation (city/state/borough) | TTL expiry only |
| `search:v{version}:{hash}` | `backend/app/services/search/search_cache.py:168` | 300s | NL search response payload | search:current_version bump |
| `search:current_version` | `backend/app/services/search/search_cache.py:232` | 30 days (when set via cache.set) | Search response cache version | Increment on invalidation |
| `parsed:{region}:{hash}` | `backend/app/services/search/search_cache.py:320` | 3600s | Parsed query payload | TTL expiry or search invalidation policy change |
| `geo:{region}:{normalized_location}` | `backend/app/services/search/search_cache.py:454` | 7 days | Geocoded location for search | TTL expiry |
| `embed:{model}:{query_hash}` | `backend/app/services/search/embedding_service.py:192` | 24h | Embedding vector | TTL expiry or model change |
| `embed:{model}:{query_hash}:computing` | `backend/app/services/search/embedding_service.py:165` | 30s | Singleflight lock token | TTL expiry |
| `{namespace}:idem:{digest}` | `backend/app/idempotency/cache.py:26` | 86400s | Idempotency response payload | TTL expiry |
| `{namespace}:lock:{key}` | `backend/app/ratelimit/locks.py:15` | 30s default | Rate-limit lock timestamp | TTL expiry or explicit delete |
| `{namespace}:{bucket}:{identity}` | `backend/app/ratelimit/redis_backend.py:33 (GCRA_LUA)` | none (no expiry set) | GCRA theoretical arrival time (ms) | Manual delete if needed |
| `analytics:last_run` | `backend/app/commands/analytics.py:212` | 7 days | Last analytics job status | TTL expiry or next run |
| `{repo_prefix}:{method}:{args...}[:kw_{hash}]` | `backend/app/repositories/cached_repository_mixin.py:334` | decorator ttl or tier default | Serialized repository results | Manual delete_pattern/clear_prefix or TTL |

## Invalidation-Only or Legacy Patterns (No Set Found)

| Cache Key Pattern | Reference Location | Note |
|---|---|---|
| `favorites:list:{student_id}` | `backend/app/services/favorites_service.py:315` | Invalidated only; no set found |
| `instructor:profile:{user_id}` | `backend/app/services/instructor_service.py:948` | Invalidated only; no set found |
| `ratings:instructor:{instructor_id}` | `backend/app/services/review_service.py:667` | Legacy invalidation only; no set found |
| `ratings:search:{instructor_id}:all` | `backend/app/services/review_service.py:668` | Legacy invalidation only; no set found |
| `week_availability:{instructor_id}:{week_start}` | `backend/app/services/availability_service.py:2148` | Invalidated only; no set found |
| `instructor_availability:{instructor_id}` | `backend/app/services/availability_service.py:2125` | Invalidated only; no set found |
| `instructor_availability:{instructor_id}:{date}` | `backend/app/services/availability_service.py:2129` | Invalidated only; no set found |
| `booking_stats:student:{student_id}` | `backend/app/services/booking_service.py:2375` | Invalidated only; no set found |
| `user_bookings:{user_id}` | `backend/app/services/booking_service.py:2384` | Invalidated only; no set found |
| `bookings:date:{date}` | `backend/app/services/booking_service.py:2388` | Invalidated only; no set found |
| `instructor_stats:{instructor_id}` | `backend/app/services/booking_service.py:2396` | Invalidated only; no set found |
| `instructor:service_area_context:{instructor_id}` | `backend/app/services/address_service.py:337` | Invalidated only; no set found |

## In-Memory Cache Keys (Non-Redis)

| Cache | Key Pattern | TTL | Data Cached | Should Invalidate When |
|---|---|---|---|---|
| PermissionChecker._cache | `any:{sorted_permissions}`, `all:{sorted_permissions}`, `{permission_name}` | process lifetime | Permission dependency callables | Process restart or code reload |
