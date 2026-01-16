import os
import base64
from datetime import datetime
from functools import wraps
from io import BytesIO

import qrcode
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session,
    redirect,
    url_for,
    send_file,
    abort,
    flash,
)
from werkzeug.security import generate_password_hash, check_password_hash

from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .database import (
    init_db,
    get_user_by_qr,
    get_user_by_id,
    list_users,
    create_user,
    insert_event,
    list_events,
    get_event_by_id,
    get_admin_password_hash,
    set_admin_password_hash,
    update_user_qr_expires_at,
    delete_user,
)
from .liveness import is_live_from_base64_frames
from .face_utils import (
    compare_face_with_user,
    extract_face_encoding_from_base64_image,
    extract_face_encoding_from_image_bytes,
)
from .time_utils import now_poland_iso, now_poland_naive


ADMIN_SESSION_KEY = "admin_logged_in"


def _now_iso() -> str:
    return now_poland_iso()


def _date_to_iso_start(date_str: str) -> str:
    return f"{date_str}T00:00:00"


def _date_to_iso_end(date_str: str) -> str:
    return f"{date_str}T23:59:59"


def _decode_data_url_to_bytes(data_url_or_b64: str) -> tuple[str, bytes]:
    """
    Zwraca (mime, bytes). Obsługuje data URL (data:image/jpeg;base64,...) albo czysty base64.
    """
    if not data_url_or_b64:
        raise ValueError("Brak danych obrazu.")

    mime = "image/jpeg"
    b64 = data_url_or_b64

    if data_url_or_b64.startswith("data:") and "," in data_url_or_b64:
        header, b64 = data_url_or_b64.split(",", 1)
        # header: data:image/jpeg;base64
        try:
            mime = header.split(";")[0].split(":", 1)[1]
        except Exception:
            mime = "image/jpeg"

    return mime, base64.b64decode(b64)


def create_app(db_path: str | None = None):
    base_dir = os.path.abspath(os.path.dirname(__file__))
    resolved_db_path = db_path or os.path.join(base_dir, "database.sqlite3")

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config["DATABASE_PATH"] = resolved_db_path
    # Sesje do panelu admina
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)

    # Ensure DB exists
    init_db(resolved_db_path)

    def admin_required(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not session.get(ADMIN_SESSION_KEY):
                return redirect(url_for("admin_login", next=request.path))
            return view_func(*args, **kwargs)

        return wrapped

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/verify", methods=["POST"])
    def verify():
        data = request.get_json(silent=True) or {}
        qr_code = (data.get("qr_code") or "").strip()
        frames = data.get("frames") or []
        direction = (data.get("direction") or "IN").upper()
        if direction not in ("IN", "OUT"):
            direction = "UNKNOWN"

        attempt_image_b64 = frames[-1] if frames else None
        now_iso = _now_iso()

        if not qr_code or not frames:
            # Logujemy jako błąd systemowy/niepełne dane (bez user_id)
            try:
                insert_event(
                    app.config["DATABASE_PATH"],
                    None,
                    now_iso,
                    direction,
                    "FAIL",
                    error_code="MISSING_DATA",
                    qr_code=qr_code or None,
                    attempt_image_b64=attempt_image_b64,
                )
            except Exception:
                pass
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Brak wymaganych danych (kod QR lub klatki wideo).",
                    }
                ),
                400,
            )

        db_path_local = app.config["DATABASE_PATH"]

        # 1. Liveness check
        is_live = is_live_from_base64_frames(frames)
        if not is_live:
            insert_event(
                db_path_local,
                None,
                now_iso,
                direction,
                "FAIL",
                error_code="NO_BLINK",
                qr_code=qr_code,
                attempt_image_b64=attempt_image_b64,
            )
            return (
                jsonify(
                    {
                        "status": "spoofing",
                        "message": "Wykryto próbę oszustwa (Spoofing) – brak mrugnięcia.",
                    }
                ),
                200,
            )

        # 2. Identyfikacja po kodzie QR i porównanie twarzy
        user = get_user_by_qr(db_path_local, qr_code)
        if not user:
            insert_event(
                db_path_local,
                None,
                now_iso,
                direction,
                "FAIL",
                error_code="UNKNOWN_QR",
                qr_code=qr_code,
                attempt_image_b64=attempt_image_b64,
            )
            return (
                jsonify(
                    {
                        "status": "fraud",
                        "message": "Nie znaleziono użytkownika o podanym kodzie QR.",
                    }
                ),
                200,
            )

        # 2a. Sprawdzenie ważności QR (jeśli ustawione)
        expires_at = user.get("qr_expires_at")
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if now_poland_naive() > exp_dt:
                    insert_event(
                        db_path_local,
                        user["id"],
                        now_iso,
                        direction,
                        "FAIL",
                        error_code="QR_EXPIRED",
                        qr_code=qr_code,
                        attempt_image_b64=attempt_image_b64,
                    )
                    return (
                        jsonify(
                            {
                                "status": "expired",
                                "message": "Kod QR utracił ważność (wygasł). Skontaktuj się z administratorem.",
                            }
                        ),
                        200,
                    )
            except Exception:
                # jeśli format daty jest zły, nie blokujemy weryfikacji
                pass

        # używamy ostatniej klatki jako referencji do identyfikacji
        is_match = compare_face_with_user(db_path_local, user, attempt_image_b64)

        if not is_match:
            insert_event(
                db_path_local,
                user["id"],
                now_iso,
                direction,
                "FAIL",
                error_code="FACE_MISMATCH",
                qr_code=qr_code,
                attempt_image_b64=attempt_image_b64,
            )
            return (
                jsonify(
                    {
                        "status": "fraud",
                        "message": "Twarz nie pasuje do użytkownika powiązanego z kodem QR.",
                    }
                ),
                200,
            )

        # 3. Zapis zdarzenia – sukces (wejście/wyjście)
        insert_event(
            db_path_local,
            user["id"],
            now_iso,
            direction,
            "OK",
            error_code=None,
            qr_code=qr_code,
            attempt_image_b64=None,
        )

        return jsonify(
            {
                "status": "success",
                "message": f"Użytkownik {user['name']} poprawnie zweryfikowany. Zapisano: {'WEJŚCIE' if direction == 'IN' else 'WYJŚCIE' if direction == 'OUT' else 'ZDARZENIE'}.",
            }
        )

    # -------------------- PANEL ADMINISTRACYJNY --------------------

    @app.route("/admin", methods=["GET"])
    @admin_required
    def admin_root():
        return redirect(url_for("admin_employees"))

    @app.route("/admin/setup", methods=["GET", "POST"])
    def admin_setup():
        db_path_local = app.config["DATABASE_PATH"]
        existing_hash = get_admin_password_hash(db_path_local)
        if existing_hash:
            return redirect(url_for("admin_login"))

        if request.method == "POST":
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""

            if len(password) < 8:
                flash("Hasło musi mieć co najmniej 8 znaków.", "error")
            elif password != confirm:
                flash("Hasła nie są identyczne.", "error")
            else:
                set_admin_password_hash(db_path_local, generate_password_hash(password))
                flash("Hasło administratora zostało ustawione. Możesz się zalogować.", "success")
                return redirect(url_for("admin_login"))

        return render_template("admin/setup.html")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        db_path_local = app.config["DATABASE_PATH"]
        password_hash = get_admin_password_hash(db_path_local)
        if not password_hash:
            return redirect(url_for("admin_setup"))

        if request.method == "POST":
            password = request.form.get("password") or ""
            if check_password_hash(password_hash, password):
                session[ADMIN_SESSION_KEY] = True
                next_url = request.args.get("next") or url_for("admin_employees")
                return redirect(next_url)
            flash("Nieprawidłowe hasło administratora.", "error")

        return render_template("admin/login.html")

    @app.route("/admin/logout", methods=["GET"])
    @admin_required
    def admin_logout():
        session.pop(ADMIN_SESSION_KEY, None)
        return redirect(url_for("admin_login"))

    @app.route("/admin/employees", methods=["GET", "POST"])
    @admin_required
    def admin_employees():
        db_path_local = app.config["DATABASE_PATH"]

        if request.method == "POST":
            first_name = request.form.get("first_name") or ""
            last_name = request.form.get("last_name") or ""
            expires_date = (request.form.get("qr_expires_at") or "").strip()  # YYYY-MM-DD
            face_b64 = (request.form.get("face_image_b64") or "").strip()
            face_file = request.files.get("face_image")

            qr_expires_at_iso = _date_to_iso_end(expires_date) if expires_date else None
            now_iso = _now_iso()

            try:
                if face_b64:
                    face_encoding_json = extract_face_encoding_from_base64_image(face_b64)
                else:
                    if not face_file or not getattr(face_file, "filename", ""):
                        raise ValueError("Dodaj obraz twarzy (plik) albo zrób zdjęcie z kamery.")
                    face_encoding_json = extract_face_encoding_from_image_bytes(face_file.read())

                user_id, qr_code = create_user(
                    db_path_local,
                    first_name=first_name,
                    last_name=last_name,
                    face_encoding_json=face_encoding_json,
                    qr_expires_at_iso=qr_expires_at_iso,
                    created_at_iso=now_iso,
                )
                flash(f"Dodano pracownika ID {user_id}. Wygenerowano QR: {qr_code}", "success")
                return redirect(url_for("admin_employees", created=str(user_id)))
            except Exception as e:
                flash(str(e), "error")

        users = list_users(db_path_local)
        created = request.args.get("created")
        created_user = None
        if created and str(created).isdigit():
            created_user = get_user_by_id(db_path_local, int(created))

        return render_template("admin/employees.html", users=users, created_user=created_user)

    @app.route("/admin/employees/<int:user_id>/qr.png", methods=["GET"])
    @admin_required
    def admin_employee_qr_png(user_id: int):
        db_path_local = app.config["DATABASE_PATH"]
        user = get_user_by_id(db_path_local, user_id)
        if not user:
            abort(404)

        payload = user.get("qr_code") or f"EMP:{user_id}"
        img = qrcode.make(payload)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        return send_file(
            buf,
            mimetype="image/png",
            as_attachment=True,
            download_name=f"qr_pracownik_{user_id}.png",
        )

    @app.route("/admin/employees/<int:user_id>/expires_at", methods=["POST"])
    @admin_required
    def admin_employee_update_expires_at(user_id: int):
        db_path_local = app.config["DATABASE_PATH"]
        user = get_user_by_id(db_path_local, user_id)
        if not user:
            return jsonify({"status": "error", "message": "Nie znaleziono użytkownika."}), 404

        data = request.get_json(silent=True) or {}
        expires_date = (data.get("qr_expires_at") or "").strip()  # YYYY-MM-DD

        if not expires_date:
            return jsonify({"status": "error", "message": "Data wygaśnięcia jest wymagana."}), 400

        try:
            qr_expires_at_iso = _date_to_iso_end(expires_date)
            success = update_user_qr_expires_at(db_path_local, user_id, qr_expires_at_iso)
            if success:
                flash(f"Zaktualizowano datę wygaśnięcia QR dla pracownika ID {user_id}.", "success")
                return jsonify({"status": "success", "message": "Data wygaśnięcia została zaktualizowana."})
            else:
                return jsonify({"status": "error", "message": "Nie udało się zaktualizować daty."}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

    @app.route("/admin/employees/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_employee_delete(user_id: int):
        db_path_local = app.config["DATABASE_PATH"]
        user = get_user_by_id(db_path_local, user_id)
        if not user:
            return jsonify({"status": "error", "message": "Nie znaleziono użytkownika."}), 404

        try:
            success = delete_user(db_path_local, user_id)
            if success:
                flash(f"Usunięto pracownika ID {user_id} ({user.get('name', '')}).", "success")
                return jsonify({"status": "success", "message": "Użytkownik został usunięty."})
            else:
                return jsonify({"status": "error", "message": "Nie udało się usunąć użytkownika."}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/admin/reports", methods=["GET"])
    @admin_required
    def admin_reports():
        db_path_local = app.config["DATABASE_PATH"]
        start_date = (request.args.get("start") or "").strip()  # YYYY-MM-DD
        end_date = (request.args.get("end") or "").strip()  # YYYY-MM-DD

        start_iso = _date_to_iso_start(start_date) if start_date else None
        end_iso = _date_to_iso_end(end_date) if end_date else None

        events = list_events(db_path_local, start_iso=start_iso, end_iso=end_iso)

        return render_template(
            "admin/reports.html",
            events=events,
            start_date=start_date,
            end_date=end_date,
        )

    @app.route("/admin/reports/pdf", methods=["GET"])
    @admin_required
    def admin_reports_pdf():
        db_path_local = app.config["DATABASE_PATH"]
        start_date = (request.args.get("start") or "").strip()
        end_date = (request.args.get("end") or "").strip()

        start_iso = _date_to_iso_start(start_date) if start_date else None
        end_iso = _date_to_iso_end(end_date) if end_date else None

        events = list_events(db_path_local, start_iso=start_iso, end_iso=end_iso)

        # Rejestracja fontów z obsługą polskich znaków (Windows)
        # Jeśli font nie istnieje, ReportLab zgłosi błąd przy pierwszym użyciu.
        try:
            pdfmetrics.registerFont(TTFont("Arial", r"C:\Windows\Fonts\arial.ttf"))
        except Exception:
            pass
        try:
            pdfmetrics.registerFont(TTFont("Arial-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
        except Exception:
            pass

        buf = BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        page_w, page_h = A4
        left = 18 * mm
        top = page_h - 18 * mm
        y = top

        # Nagłówek raportu
        font_title = "Arial-Bold" if "Arial-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
        font_text = "Arial" if "Arial" in pdfmetrics.getRegisteredFontNames() else "Helvetica"

        c.setFont(font_title, 14)
        c.drawString(left, y, "Raport wejść / wyjść (QR + twarz)")
        y -= 8 * mm
        c.setFont(font_text, 10)
        zakres = f"{start_date or '-'} — {end_date or '-'}"
        c.drawString(left, y, f"Zakres: {zakres}")
        y -= 10 * mm

        # Nagłówek kolumn
        c.setFont(font_text, 9)
        header_line = "Data / godzina | Status | Kierunek | ID pracownika | Pracownik | Kod błędu"
        c.drawString(left, y, header_line)
        y -= 6 * mm

        c.setFont(font_text, 9)

        for ev in events:
            ts = ev.get("timestamp") or ""
            # Format daty: dd mm rrrr hh:mm:ss
            ts_formatted = ts
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    ts_formatted = dt.strftime("%d %m %Y %H:%M:%S")
                except Exception:
                    # Jeśli nie uda się sparsować, zostawiamy oryginalny tekst
                    ts_formatted = ts
            status = ev.get("status") or ""
            direction = ev.get("direction") or ""
            uid = ev.get("user_id")
            uname = ev.get("user_name") or "-"
            err = ev.get("error_code") or ""

            line = f"{ts_formatted} | {status} | {direction} | ID: {uid if uid is not None else '-'} | {uname}"
            if status == "FAIL" and err:
                line += f" | BŁĄD: {err}"

            if y < 25 * mm:
                c.showPage()
                y = top
                c.setFont(font_text, 9)
                # Nagłówek kolumn na każdej nowej stronie
                c.drawString(left, y, header_line)
                y -= 6 * mm

            # Proste zawijanie (2 linie maks)
            max_chars = 110
            if len(line) <= max_chars:
                c.drawString(left, y, line)
                y -= 5.5 * mm
            else:
                c.drawString(left, y, line[:max_chars])
                y -= 5.5 * mm
                c.drawString(left, y, line[max_chars : max_chars * 2])
                y -= 5.5 * mm

            if status == "FAIL" and ev.get("attempt_image_b64"):
                try:
                    mime, img_bytes = _decode_data_url_to_bytes(ev["attempt_image_b64"])
                    img_reader = ImageReader(BytesIO(img_bytes))
                    img_w = 60 * mm
                    img_h = 45 * mm

                    if y - img_h < 25 * mm:
                        c.showPage()
                        y = top
                        # Ustaw font z obsługą polskich znaków + nagłówek kolumn na nowej stronie
                        c.setFont(font_text, 9)
                        c.drawString(left, y, header_line)
                        y -= 6 * mm

                    c.setFont(font_text, 9)
                    c.drawString(left, y, f"Zdjęcie próby ({mime}):")
                    y -= 5.5 * mm
                    c.drawImage(
                        img_reader,
                        left,
                        y - img_h,
                        width=img_w,
                        height=img_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    y -= img_h + 6 * mm
                except Exception:
                    # jeśli obraz jest uszkodzony, nie blokujemy generowania PDF
                    y -= 2 * mm

        c.save()
        buf.seek(0)

        filename = "raport_wejsc_wyjsc.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)

    @app.route("/admin/events/<int:event_id>/image", methods=["GET"])
    @admin_required
    def admin_event_image(event_id: int):
        db_path_local = app.config["DATABASE_PATH"]
        ev = get_event_by_id(db_path_local, event_id)
        if not ev or not ev.get("attempt_image_b64"):
            abort(404)

        mime, img_bytes = _decode_data_url_to_bytes(ev["attempt_image_b64"])
        return send_file(BytesIO(img_bytes), mimetype=mime)

    return app


if __name__ == "__main__":
    import ssl
    
    # Import generate_cert - próbuj relatywny, jeśli nie działa - bezwzględny
    try:
        from .generate_cert import generate_self_signed_cert
    except ImportError:
        from generate_cert import generate_self_signed_cert
    
    app = create_app()
    
    # Sprawdź czy certyfikaty istnieją, jeśli nie - wygeneruj je
    base_dir = os.path.abspath(os.path.dirname(__file__))
    cert_path = os.path.join(base_dir, 'cert.pem')
    key_path = os.path.join(base_dir, 'key.pem')
    
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print("🔐 Certyfikaty SSL nie zostały znalezione. Generowanie...")
        cert_path, key_path = generate_self_signed_cert(force=True)
        if not cert_path or not key_path:
            print("❌ Nie udało się wygenerować certyfikatów. Uruchamiam serwer bez HTTPS.")
            app.run(host="0.0.0.0", port=5000, debug=True)
        else:
            print(f"✅ Uruchamianie serwera HTTPS na porcie 5000...")
            print(f"   URL: https://localhost:5000")
            app.run(host="0.0.0.0", port=5000, debug=True, ssl_context=(cert_path, key_path))
    else:
        print(f"✅ Uruchamianie serwera HTTPS na porcie 5000...")
        print(f"   URL: https://localhost:5000")
        app.run(host="0.0.0.0", port=5000, debug=True, ssl_context=(cert_path, key_path))


