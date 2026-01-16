from pathlib import Path

import backend.database as db


def _init_tmp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.sqlite3"
    db.init_db(str(db_path))
    return str(db_path)


def test_create_user_and_list(tmp_path):
    db_path = _init_tmp_db(tmp_path)
    created_at = "2026-01-16T12:00:00"
    user_id, qr_code = db.create_user(
        db_path=db_path,
        first_name="Jan",
        last_name="Kowalski",
        face_encoding_json="[]",
        qr_expires_at_iso="2099-12-31T23:59:59",
        created_at_iso=created_at,
    )

    users = db.list_users(db_path)
    assert len(users) == 1
    assert users[0]["id"] == user_id
    assert users[0]["qr_code"] == qr_code
    assert users[0]["created_at"] == created_at
    assert users[0]["updated_at"] == created_at


def test_update_user_qr_expires_at_updates_updated_at(tmp_path, monkeypatch):
    db_path = _init_tmp_db(tmp_path)
    created_at = "2026-01-16T10:00:00"
    user_id, _ = db.create_user(
        db_path=db_path,
        first_name="Anna",
        last_name="Nowak",
        face_encoding_json="[]",
        qr_expires_at_iso="2026-12-31T23:59:59",
        created_at_iso=created_at,
    )

    monkeypatch.setattr(db, "now_poland_iso", lambda: "2026-01-16T11:11:11")
    assert db.update_user_qr_expires_at(db_path, user_id, "2099-12-31T23:59:59")

    user = db.get_user_by_id(db_path, user_id)
    assert user["qr_expires_at"] == "2099-12-31T23:59:59"
    assert user["updated_at"] == "2026-01-16T11:11:11"


def test_list_events_filters_and_order(tmp_path):
    db_path = _init_tmp_db(tmp_path)
    user_id, _ = db.create_user(
        db_path=db_path,
        first_name="Ola",
        last_name="Zielinska",
        face_encoding_json="[]",
        qr_expires_at_iso="2099-12-31T23:59:59",
        created_at_iso="2026-01-16T09:00:00",
    )

    db.insert_event(db_path, user_id, "2026-01-15T10:00:00", "IN", "OK")
    db.insert_event(db_path, user_id, "2026-01-16T09:00:00", "OUT", "OK")
    db.insert_event(db_path, None, "2026-01-17T08:00:00", "IN", "FAIL", error_code="X")

    filtered = db.list_events(
        db_path, start_iso="2026-01-16T00:00:00", end_iso="2026-01-16T23:59:59"
    )
    assert len(filtered) == 1
    assert filtered[0]["timestamp"] == "2026-01-16T09:00:00"

    all_events = db.list_events(db_path)
    assert all_events[0]["timestamp"] == "2026-01-17T08:00:00"

