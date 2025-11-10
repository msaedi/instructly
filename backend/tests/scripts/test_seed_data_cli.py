import sys

from scripts import seed_data


def test_seed_data_system_only_does_not_print_skip(monkeypatch, capsys):
    monkeypatch.setattr(seed_data, "_print_banner", lambda: None)
    monkeypatch.setattr(seed_data, "seed_system_data", lambda verbose=True: print("SYSTEM"))
    monkeypatch.setattr(seed_data, "seed_mock_data", lambda *args, **kwargs: print("MOCK"))
    monkeypatch.setattr(sys, "argv", ["seed_data.py", "--system-only"])

    result = seed_data.main()
    assert result == 0

    output = capsys.readouterr().out
    assert "SYSTEM" in output
    assert "Skipping mock users" not in output


def test_seed_data_without_flags_prints_skip(monkeypatch, capsys):
    monkeypatch.setattr(seed_data, "_print_banner", lambda: None)
    monkeypatch.setattr(seed_data, "seed_system_data", lambda verbose=True: print("SYSTEM"))
    monkeypatch.setattr(seed_data, "seed_mock_data", lambda *args, **kwargs: print("MOCK"))
    monkeypatch.setattr(sys, "argv", ["seed_data.py"])

    result = seed_data.main()
    assert result == 0
    output = capsys.readouterr().out
    assert "Skipping mock users/instructors/bookings" in output
