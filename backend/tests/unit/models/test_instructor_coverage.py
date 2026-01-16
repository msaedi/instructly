from __future__ import annotations

from app.models.instructor import InstructorProfile


class DummyCounter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1


class DummyLabelCounter(DummyCounter):
    def labels(self, **_kwargs):
        return self


def test_bgc_report_id_handles_empty() -> None:
    instructor = InstructorProfile()
    instructor._bgc_report_id = None

    assert instructor.bgc_report_id is None

    instructor.bgc_report_id = ""
    assert instructor._bgc_report_id == ""


def test_bgc_report_id_decrypts_and_encrypts(monkeypatch) -> None:
    import app.core.crypto as crypto
    import app.core.metrics as metrics

    decrypt_counter = DummyCounter()
    encrypt_counter = DummyLabelCounter()

    monkeypatch.setattr(metrics, "BGC_REPORT_ID_DECRYPT_TOTAL", decrypt_counter)
    monkeypatch.setattr(metrics, "BGC_REPORT_ID_ENCRYPT_TOTAL", encrypt_counter)

    monkeypatch.setattr(crypto, "encrypt_report_token", lambda value: f"enc:{value}")
    monkeypatch.setattr(crypto, "decrypt_report_token", lambda value: value.replace("enc:", ""))

    instructor = InstructorProfile()
    instructor.bgc_report_id = "report-1"

    assert instructor._bgc_report_id.startswith("enc:")
    assert encrypt_counter.count == 1

    assert instructor.bgc_report_id == "report-1"
    assert decrypt_counter.count == 1


def test_bgc_report_id_decrypt_value_error(monkeypatch) -> None:
    import app.core.crypto as crypto

    monkeypatch.setattr(crypto, "decrypt_report_token", lambda _value: (_ for _ in ()).throw(ValueError()))

    instructor = InstructorProfile()
    instructor._bgc_report_id = "raw-token"

    assert instructor.bgc_report_id == "raw-token"
