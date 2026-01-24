from app.constants.payment_status import PaymentDisplayStatus, map_payment_status


def test_map_payment_status_defaults_to_pending() -> None:
    assert map_payment_status(None) == PaymentDisplayStatus.PENDING.value


def test_map_payment_status_unknown_passthrough() -> None:
    assert map_payment_status("custom_status") == "custom_status"


def test_map_payment_status_known_mapping() -> None:
    assert map_payment_status("requires_capture") == PaymentDisplayStatus.AUTHORIZED.value
