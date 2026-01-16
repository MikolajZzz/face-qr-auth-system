from datetime import datetime

import backend.app as app_module
from backend.database import create_user, list_events


def test_verify_expired_qr_records_event(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite3"
    app = app_module.create_app(db_path=str(db_path))
    app.config["TESTING"] = True

    fixed_now = datetime(2026, 1, 16, 12, 0, 0)
    fixed_now_iso = "2026-01-16T12:00:00"

    monkeypatch.setattr(app_module, "now_poland_naive", lambda: fixed_now)
    monkeypatch.setattr(app_module, "now_poland_iso", lambda: fixed_now_iso)
    monkeypatch.setattr(app_module, "is_live_from_base64_frames", lambda frames: True)
    monkeypatch.setattr(app_module, "compare_face_with_user", lambda db_path, user, frame: True)

    _, qr_code = create_user(
        db_path=str(db_path),
        first_name="Jan",
        last_name="Kowalski",
        face_encoding_json="[]",
        qr_expires_at_iso="2026-01-16T11:00:00",
        created_at_iso=fixed_now_iso,
    )

    client = app.test_client()
    response = client.post(
        "/verify",
        json={"qr_code": qr_code, "frames": ["dummy"], "direction": "IN"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "expired"

    events = list_events(str(db_path))
    assert len(events) == 1
    assert events[0]["error_code"] == "QR_EXPIRED"
    assert events[0]["timestamp"] == fixed_now_iso

