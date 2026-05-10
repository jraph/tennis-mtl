"""Generate a self-signed TLS cert/key pair if they don't already exist."""
from __future__ import annotations

import sys
from pathlib import Path

from OpenSSL import crypto


def ensure_cert(cert_path: Path, key_path: Path) -> None:
    if cert_path.exists() and key_path.exists():
        return

    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)

    cert = crypto.X509()
    cert.get_subject().CN = "tennis-mtl"
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(key)
    cert.sign(key, "sha256")

    cert_path.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    key_path.write_bytes(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
    key_path.chmod(0o600)


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    ensure_cert(root / "cert.pem", root / "key.pem")
