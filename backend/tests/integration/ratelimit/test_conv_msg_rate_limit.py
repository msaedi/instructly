"""Tests for conv_msg rate limit bucket behavior."""
from app.ratelimit.config import BUCKETS
from app.ratelimit.gcra import gcra_decide


class TestConvMsgRateLimitConfig:
    def test_conv_msg_bucket_exists(self) -> None:
        assert "conv_msg" in BUCKETS

    def test_conv_msg_has_burst_capacity(self) -> None:
        config = BUCKETS["conv_msg"]
        assert config["burst"] > 0, "conv_msg must allow bursts for normal chat"
        assert config["burst"] >= 5, "conv_msg should allow at least 5 rapid messages"

    def test_conv_msg_rate_allows_normal_chat(self) -> None:
        config = BUCKETS["conv_msg"]
        assert config["rate_per_min"] >= 30


class TestConvMsgGCRABehavior:
    def test_burst_messages_allowed(self) -> None:
        config = BUCKETS["conv_msg"]
        last_tat = None
        now_s = 1000.0
        allowed_flags = []

        for i in range(config["burst"]):
            last_tat, decision = gcra_decide(
                now_s=now_s + (i * 0.1),
                last_tat_s=last_tat,
                rate_per_min=config["rate_per_min"],
                burst=config["burst"],
            )
            allowed_flags.append(decision.allowed)

        assert all(allowed_flags)

    def test_two_quick_messages_allowed(self) -> None:
        config = BUCKETS["conv_msg"]
        last_tat, decision = gcra_decide(
            now_s=0.0,
            last_tat_s=None,
            rate_per_min=config["rate_per_min"],
            burst=config["burst"],
        )
        assert decision.allowed

        last_tat, decision = gcra_decide(
            now_s=2.0,
            last_tat_s=last_tat,
            rate_per_min=config["rate_per_min"],
            burst=config["burst"],
        )
        assert decision.allowed

    def test_rapid_conversation_allowed(self) -> None:
        config = BUCKETS["conv_msg"]
        last_tat = None
        times = [0.0, 2.0, 4.0, 6.0, 8.0]
        allowed_flags = []

        for now_s in times:
            last_tat, decision = gcra_decide(
                now_s=now_s,
                last_tat_s=last_tat,
                rate_per_min=config["rate_per_min"],
                burst=config["burst"],
            )
            allowed_flags.append(decision.allowed)

        assert all(allowed_flags)
