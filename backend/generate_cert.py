#!/usr/bin/env python3
"""
Skrypt do generowania self-signed certyfikatów SSL dla lokalnego rozwoju.
Generuje cert.pem i key.pem w katalogu backend/.
"""
import os
import sys
import ipaddress
from datetime import datetime, timedelta

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("   Biblioteka 'cryptography' nie jest zainstalowana.")
    print("   Zainstaluj ją poleceniem: pip install cryptography")
    sys.exit(1)


def generate_self_signed_cert(force=False):
    """Generuje self-signed certyfikat SSL i klucz prywatny.
    
    Args:
        force: Jeśli True, nadpisuje istniejące certyfikaty bez pytania.
    
    Returns:
        tuple: (cert_path, key_path) lub (None, None) jeśli anulowano
    """
    base_dir = os.path.abspath(os.path.dirname(__file__))
    cert_path = os.path.join(base_dir, 'cert.pem')
    key_path = os.path.join(base_dir, 'key.pem')
    
    # Sprawdź czy certyfikaty już istnieją
    if not force and (os.path.exists(cert_path) or os.path.exists(key_path)):
        print("    Certyfikaty już istnieją!")
        if sys.stdin.isatty():  # Tylko jeśli uruchomiono interaktywnie
            response = input("   Czy chcesz je nadpisać? (tak/nie): ").strip().lower()
            if response not in ['tak', 't', 'yes', 'y']:
                print("   Anulowano.")
                return None, None
        else:
            # W trybie nieinteraktywnym, nie nadpisuj
            print(f"   Używam istniejących certyfikatów.")
            return cert_path, key_path
    
    print("   Generowanie certyfikatów SSL...")
    
    # Generuj klucz prywatny
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )
    
    # Utwórz certyfikat
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "PL"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Poland"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Face QR Auth System"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    # Zapisz klucz prywatny
    with open(key_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Zapisz certyfikat
    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print(f"   Certyfikaty wygenerowane pomyślnie!")
    print(f"   Certyfikat: {cert_path}")
    print(f"   Klucz: {key_path}")
    print(f"   Przeglądarka pokaże ostrzeżenie o bezpieczeństwie - to normalne.")
    print(f"   Po pierwszym wejściu zaakceptuj certyfikat w przeglądarce.")
    
    return cert_path, key_path


if __name__ == "__main__":
    generate_self_signed_cert()

