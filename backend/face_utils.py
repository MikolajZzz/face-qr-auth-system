import base64
import json
from datetime import datetime
from typing import Dict, Any, Tuple

import cv2
import numpy as np
import face_recognition

from .database import get_connection, create_user


def _decode_base64_to_rgb(b64_string: str) -> np.ndarray:
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]

    img_data = base64.b64decode(b64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb


def _decode_bytes_to_rgb(image_bytes: bytes) -> np.ndarray:
    """
    Dekoduje bytes (np. z uploadu) do RGB (numpy array) albo None.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return rgb
    except Exception:
        return None


def extract_face_encoding_from_rgb(rgb_image: np.ndarray) -> str:
    """
    Zwraca face encoding jako JSON string (lista floatów) lub rzuca ValueError.
    """
    if rgb_image is None:
        raise ValueError("Nie udało się zdekodować obrazu.")

    boxes = face_recognition.face_locations(rgb_image)
    encodings = face_recognition.face_encodings(rgb_image, boxes)
    if not encodings:
        raise ValueError("Nie wykryto twarzy na obrazie.")

    encoding = encodings[0]
    return json.dumps(encoding.tolist())


def extract_face_encoding_from_base64_image(b64_string: str) -> str:
    rgb = _decode_base64_to_rgb(b64_string)
    return extract_face_encoding_from_rgb(rgb)


def extract_face_encoding_from_image_bytes(image_bytes: bytes) -> str:
    rgb = _decode_bytes_to_rgb(image_bytes)
    return extract_face_encoding_from_rgb(rgb)


def compare_face_with_user(db_path: str, user_row: Dict[str, Any], frame_b64: str) -> bool:
    """
    Pobiera zakodowaną twarz użytkownika z DB i porównuje z twarzą
    wyciągniętą z przesłanej klatki (frame_b64).
    """
    rgb_image = _decode_base64_to_rgb(frame_b64)
    if rgb_image is None:
        return False

    boxes = face_recognition.face_locations(rgb_image)
    encodings = face_recognition.face_encodings(rgb_image, boxes)
    if not encodings:
        return False

    candidate_encoding = encodings[0]

    known_encoding = np.array(json.loads(user_row["face_encoding"]))

    distances = face_recognition.face_distance([known_encoding], candidate_encoding)
    distance = float(distances[0])

    # domyślny próg z biblioteki face_recognition to ok. 0.6
    return distance < 0.6


def add_user_with_image(
    db_path: str,
    first_name: str,
    last_name: str,
    image_path: str,
    qr_expires_at_iso: str,
) -> Tuple[int, str]:
    """
    Pomocnicza funkcja (DEV) do dodawania pracownika na podstawie
    pojedynczego zdjęcia na dysku. Zapisuje w bazie tylko face encoding.
    Zwraca (ID, payload QR) gdzie payload ma format "EMP:{id}".
    """
    image = face_recognition.load_image_file(image_path)
    encoding_json = extract_face_encoding_from_rgb(image)

    now_iso = datetime.utcnow().replace(microsecond=0).isoformat()
    user_id, qr_code = create_user(
        db_path=db_path,
        first_name=first_name,
        last_name=last_name,
        face_encoding_json=encoding_json,
        qr_expires_at_iso=qr_expires_at_iso,
        created_at_iso=now_iso,
    )
    return user_id, qr_code


