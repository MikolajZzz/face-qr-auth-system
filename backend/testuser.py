import os
import sys

# Pozwala uruchomić plik bezpośrednio: `python backend/testuser.py`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import init_db
from backend.face_utils import add_user_with_image

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # katalog projektu
db_path = os.path.join(base_dir, "backend", "database.sqlite3")

init_db(db_path)

user_id, qr_code = add_user_with_image(
    db_path=db_path,
    first_name="Mati",
    last_name="A",
    image_path=r"C:\Users\mateo\OneDrive\Pulpit\face-qr-auth-system\mati.jpg"
    ,
    qr_expires_at_iso="2099-12-31T23:59:59",
)

print("Dodano pracownika o ID:", user_id)
print("Payload QR:", qr_code)