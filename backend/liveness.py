import base64
from typing import List

import cv2
import numpy as np
import mediapipe as mp


LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [263, 387, 385, 362, 380, 373]

# Próg EAR poniżej którego oko uznajemy za zamknięte
EYE_AR_THRESH = 0.21
# Minimalna liczba kolejnych klatek z zamkniętym okiem, aby uznać to za mrugnięcie
EYE_AR_CONSEC_FRAMES = 2
# Minimalna liczba klatek z otwartym okiem przed rozpoczęciem sekwencji mrugania
MIN_OPEN_FRAMES_BEFORE_BLINK = 2


def _decode_base64_image(b64_string: str):
    """
    Przyjmuje data URL (data:image/jpeg;base64,...) lub czysty base64
    i zwraca obraz BGR (numpy array) lub None.
    """
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]

    try:
        img_data = base64.b64decode(b64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _eye_aspect_ratio(landmarks, eye_indices, img_w: int, img_h: int) -> float:
    points = []
    for idx in eye_indices:
        lm = landmarks[idx]
        points.append(np.array([lm.x * img_w, lm.y * img_h]))

    p1, p2, p3, p4, p5, p6 = points
    # (|p2 - p6| + |p3 - p5|) / (2 * |p1 - p4|)
    numerator = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    denominator = 2.0 * np.linalg.norm(p1 - p4)
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def is_live_from_base64_frames(frames_b64: List[str]) -> bool:
    """
    Test żywotności oparty na detekcji mrugania z pełną sekwencją:
    - Wymaga sekwencji: oko otwarte → zamknięte (min. N klatek) → otwarte
    - Zabezpiecza przed statycznymi obrazami (wymaga zmian w czasie)
    - Wykrywa naturalne mrugnięcie w czasie rzeczywistym
    
    Stany:
    - STATE_OPEN: Oko otwarte (oczekiwanie na rozpoczęcie mrugania)
    - STATE_CLOSING: Oko zaczyna się zamykać
    - STATE_CLOSED: Oko zamknięte (liczymy klatki)
    - STATE_OPENING: Oko zaczyna się otwierać (po wymaganym czasie zamknięcia)
    - STATE_COMPLETE: Pełne mrugnięcie wykryte (otwarte → zamknięte → otwarte)
    """
    decoded_frames = []
    for b64 in frames_b64:
        img = _decode_base64_image(b64)
        if img is not None:
            decoded_frames.append(img)

    # Wymagamy minimum 5 klatek, aby mieć szansę na wykrycie pełnej sekwencji mrugania
    if len(decoded_frames) < 5:
        return False

    mp_face_mesh = mp.solutions.face_mesh

    # Maszyna stanów dla detekcji mrugania
    STATE_OPEN = 0          # Oko otwarte - oczekiwanie na rozpoczęcie mrugania
    STATE_CLOSING = 1       # Oko zaczyna się zamykać
    STATE_CLOSED = 2        # Oko zamknięte - liczymy klatki
    STATE_OPENING = 3       # Oko zaczyna się otwierać (po wymaganym czasie)
    STATE_COMPLETE = 4      # Pełne mrugnięcie wykryte

    state = STATE_OPEN
    consec_closed_frames = 0  # Licznik klatek z zamkniętym okiem
    consec_open_frames = 0     # Licznik klatek z otwartym okiem (przed mruganiem)
    frames_with_face = 0       # Licznik klatek z wykrytą twarzą (zabezpieczenie przed statycznym obrazem)

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        for img in decoded_frames:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = face_mesh.process(rgb)

            if not result.multi_face_landmarks:
                # Brak twarzy - resetujemy stan (wymagamy ciągłości)
                if state != STATE_COMPLETE:
                    state = STATE_OPEN
                    consec_closed_frames = 0
                    consec_open_frames = 0
                continue

            frames_with_face += 1
            face_landmarks = result.multi_face_landmarks[0].landmark
            h, w, _ = img.shape

            left_ear = _eye_aspect_ratio(face_landmarks, LEFT_EYE_IDX, w, h)
            right_ear = _eye_aspect_ratio(face_landmarks, RIGHT_EYE_IDX, w, h)
            ear = (left_ear + right_ear) / 2.0

            # Maszyna stanów dla detekcji mrugania
            if state == STATE_OPEN:
                # Stan: Oko otwarte - oczekiwanie na rozpoczęcie mrugania
                if ear >= EYE_AR_THRESH:
                    consec_open_frames += 1
                    # Wymagamy minimum N klatek z otwartym okiem przed rozpoczęciem mrugania
                    # (zabezpieczenie przed rozpoczęciem od zamkniętego oka)
                    if consec_open_frames >= MIN_OPEN_FRAMES_BEFORE_BLINK:
                        # Gotowi na wykrycie mrugania
                        pass
                else:
                    # Oko zaczyna się zamykać
                    if consec_open_frames >= MIN_OPEN_FRAMES_BEFORE_BLINK:
                        state = STATE_CLOSING
                        consec_closed_frames = 1
                    else:
                        # Za wcześnie - reset (oko nie było wystarczająco długo otwarte)
                        consec_open_frames = 0
                        consec_closed_frames = 0

            elif state == STATE_CLOSING:
                # Stan: Oko zaczyna się zamykać
                if ear < EYE_AR_THRESH:
                    consec_closed_frames += 1
                    if consec_closed_frames >= EYE_AR_CONSEC_FRAMES:
                        # Oko było zamknięte wystarczająco długo - przechodzimy do stanu zamkniętego
                        state = STATE_CLOSED
                else:
                    # Oko otworzyło się zbyt szybko - to nie było prawdziwe mrugnięcie
                    state = STATE_OPEN
                    consec_closed_frames = 0
                    consec_open_frames = 1

            elif state == STATE_CLOSED:
                # Stan: Oko zamknięte - oczekiwanie na otwarcie
                if ear < EYE_AR_THRESH:
                    consec_closed_frames += 1
                    # Pozostajemy w stanie zamkniętym
                else:
                    # Oko zaczyna się otwierać - przechodzimy do stanu otwierania
                    state = STATE_OPENING
                    consec_open_frames = 1

            elif state == STATE_OPENING:
                # Stan: Oko otwiera się po mrugnięciu
                if ear >= EYE_AR_THRESH:
                    consec_open_frames += 1
                    # Oko jest otwarte - mrugnięcie zakończone!
                    if consec_open_frames >= MIN_OPEN_FRAMES_BEFORE_BLINK:
                        state = STATE_COMPLETE
                else:
                    # Oko znowu się zamknęło - reset (nieprawidłowa sekwencja)
                    state = STATE_OPEN
                    consec_closed_frames = 1
                    consec_open_frames = 0

            elif state == STATE_COMPLETE:
                # Stan: Pełne mrugnięcie wykryte - nie zmieniamy stanu
                pass

    # Weryfikacja: wymagamy wykrycia pełnej sekwencji ORAZ minimum kilku klatek z twarzą
    # (zabezpieczenie przed statycznym obrazem - wymagamy zmian w czasie)
    return state == STATE_COMPLETE and frames_with_face >= 5


