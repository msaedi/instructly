import redis

from .config import settings


def get_redis():
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


# Lua script implementing GCRA logic using TAT (Theoretical Arrival Time)
# KEYS[1] = storage key
# ARGV[1] = now_ms
# ARGV[2] = interval_ms (60_000 / rate_per_min)
# ARGV[3] = burst
# Returns: {allowed, retry_after_ms, remaining, limit, reset_epoch_s, new_tat_ms}
GCRA_LUA = r"""
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local interval_ms = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])

local tat_ms = redis.call('GET', key)
if tat_ms then tat_ms = tonumber(tat_ms) end

-- If no TAT, initialize to allow immediate burst requests
if not tat_ms then
  tat_ms = now_ms - (burst * interval_ms)
end

local allow = now_ms >= (tat_ms - (burst * interval_ms))
local new_tat_ms
local retry_after_ms = 0
local remaining = 0
local limit = burst + 1
local reset_epoch_s = math.floor((now_ms + (burst * interval_ms)) / 1000)

if allow then
  if tat_ms > now_ms then
    new_tat_ms = tat_ms + interval_ms
  else
    new_tat_ms = now_ms + interval_ms
  end
  remaining = math.max(0, burst - math.floor(((new_tat_ms - now_ms) / interval_ms) - 1))
  redis.call('SET', key, new_tat_ms)
  return {1, 0, remaining, limit, reset_epoch_s, new_tat_ms}
else
  local allow_at_ms = tat_ms - (burst * interval_ms)
  retry_after_ms = math.max(0, allow_at_ms - now_ms)
  -- keep tat_ms unchanged when blocked
  return {0, retry_after_ms, 0, limit, reset_epoch_s, tat_ms}
end
"""

__all__ = ["get_redis", "GCRA_LUA"]
