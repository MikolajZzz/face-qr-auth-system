# System Uwierzytelniania QR + Twarz


### Główne funkcje

- **Dwuskładnikowe uwierzytelnianie**: Kombinacja kodu QR i rozpoznawania twarzy
- **Wykrywanie autentyczności**: System wymaga mrugnięcia w czasie weryfikacji, co zapobiega użyciu zdjęć
- **Panel administracyjny**: Panel do zarządzania pracownikami
- **Raporty**: Generowanie raportów wejść/wyjść z możliwością eksportu do PDF
- **HTTPS**
- **Zarządzanie ważnością kodów QR**: Możliwość ustawienia daty wygaśnięcia kodów QR

### Proces weryfikacji

1. **Skanowanie kodu QR** - pracownik trzyma telefon/kartke kodem QR przed kamerą
2. **Nagranie wideo** - system rejestruje sekwencję klatek wideo
3. **Test żywotności** - wykrywanie mrugnięcia w sekwencji wideo 
4. **Rozpoznawanie twarzy** - porównanie twarzy z zapisanym wzorcem (wektorem twarzy)
5. **Rejestracja zdarzenia** - zapis wejścia/wyjścia w bazie danych (zdjecia fauszywych prób)

## Wymagania systemowe

- **System operacyjny**: Windows 10/11
- **Python**: 3.10 
- **CMake**: 4.2.1
- **Kamera**
- **Przeglądarka**

## Instalacja

### 1. Pobierz oraz zainstaluj CMake oraz dodaj do zmiennych systemowych
(https://cmake.org/download/).

### 2. Uruchom skrypt instalacyjny

W katalogu głównym projektu uruchom:

.\install.ps1

Po zakończeniu instalacji, uruchom aplikację:

.\run.ps1


Aplikacja zostanie uruchomiona na porcie **5000** z protokołem HTTPS:
- **URL**: `https://localhost:5000`
- **URL**: `https://adres_ip_urzadzenia:5000`

**Uwaga**: Przeglądarka może wyświetlić ostrzeżenie o certyfikacie (certyfikat jest samopodpisany).

### Konfiguracja administratora

1. Otwórz `https://adres_ip_urzadzenia:5000/admin`
2. Ustaw hasło administratora (minimum 8 znaków)
3. Zaloguj się do panelu administracyjnego

### Panel administracyjny

Dostępny pod adresem: `https://localhost:5000/admin`

#### Zarządzanie pracownikami (`/admin/employees`)

- **Dodawanie pracownika**:
  - Wprowadź imię i nazwisko
  - Zrób zdjęcie twarzy lub wgraj plik ze zdjęciem
  - Ustaw datę wygaśnięcia kodu QR
  - System automatycznie wygeneruje unikalny kod QR (format: `EMP:{id}`)

- **Zarządzanie pracownikami**:
  - Wyświetl listę wszystkich pracowników
  - Pobierz kod QR w formacie PNG
  - Zaktualizuj datę wygaśnięcia kodu QR
  - Usuń pracownika

#### Raporty (`/admin/reports`)

- **Przeglądanie zdarzeń**:
  - Filtrowanie po dacie (zakres dat)
  - Wyświetlanie wszystkich prób wejścia/wyjścia
  - Podgląd zdjęć z nieudanych prób weryfikacji

- **Eksport do PDF**:
  - Kliknij "Pobierz raport PDF"
  - Raport zawiera wszystkie zdarzenia z wybranego zakresu dni
  - Uwzględnia zdjęcia z prób nieudanych wejść

### Weryfikacja pracownika

1. Otwórz stronę główną: `https://adres_ip_urzadzenia:5000`
2. Wybierz tryb: **Wejście** lub **Wyjście** w warunkach realnych proponujemy przełącznik lub 2 systemy ustawione na każdą opcje
3. Trzymaj kod QR przed kamerą 
4. Po wykryciu kodu QR, kliknij **"Rozpocznij weryfikację"**
5. Mrugnij kilka razy
6. System zweryfikuje tożsamość i zarejestruje zdarzenie

### Backend
- **Flask 3.1.2** 
- **face-recognition 1.3.0** - Rozpoznawanie twarzy 
- **OpenCV 4.12.0** - Przetwarzanie obrazów
- **MediaPipe 0.10.14** - Wykrywanie punktów charakterystycznych twarzy 
- **SQLite** - Baza danych
- **QRCode 8.2** - Generowanie kodów QR
- **ReportLab 4.4.7** - Generowanie raportów PDF
- **cryptography 46.0.3** - Generowanie certyfikatów SSL

### Frontend
- **HTML/CSS/JavaScript** - Interfejs użytkownika
- **WebRTC** - Dostęp do kamery
- **jsQR** - Dekodowanie kodów QR 

### Bezpieczeństwo
- **Werkzeug** - Haszowanie haseł
- **HTTPS/SSL**
- Przechowywanie zdjęć twarzy jako wektor 
- **Test żywotności**: Wymaganie mrugnięcia 

##  Testy

Projekt zawiera testy jednostkowe w katalogu `tests/`, aby uruchomić testy:

python -m pytest


