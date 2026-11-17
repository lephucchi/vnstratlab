"""Encrypt the PO dashboard data before it is published (Pages build).

GitHub Pages is static and public, so a login form alone protects nothing. Instead the
dashboard data is published only as an AES-256-GCM envelope whose key is derived with
PBKDF2-HMAC-SHA256 from the PO user name and password. The browser derives the same key
from what the user types (WebCrypto) and can only decrypt with the right credentials.

Credentials come only from `vnstratlab.settings.Settings`:
VNSTRATLAB_PO_USER and VNSTRATLAB_PO_PASSWORD (environment / `.env`; GitHub secrets in CI).
They are never printed or written anywhere.

The plaintext input is always deleted. If the credentials are not set, nothing is
published and the dashboard shows that it is not configured.

Usage:
  python tools/encrypt_po.py --in _site/po/data.json --out _site/po/data.enc.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vnstratlab.settings import Settings, load_settings

ENVELOPE_VERSION = 1
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
IV_BYTES = 12


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def key_material(user: str, password: str) -> bytes:
    """What the browser feeds to PBKDF2: user and password joined by a newline."""
    return f"{user}\n{password}".encode()


def derive_key(user: str, password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", key_material(user, password), salt, iterations, dklen=32)


def encrypt(
    plaintext: bytes, user: str, password: str, iterations: int = KDF_ITERATIONS
) -> dict[str, Any]:
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    key = derive_key(user, password, salt, iterations)
    return {
        "v": ENVELOPE_VERSION,
        "alg": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256",
        "iter": iterations,
        "salt": _b64(salt),
        "iv": _b64(iv),
        "data": _b64(AESGCM(key).encrypt(iv, plaintext, None)),
    }


def decrypt(envelope: dict[str, Any], user: str, password: str) -> bytes:
    """Inverse of `encrypt` (used by tests; the browser does the same with WebCrypto)."""
    salt = base64.b64decode(envelope["salt"])
    key = derive_key(user, password, salt, int(envelope["iter"]))
    return AESGCM(key).decrypt(
        base64.b64decode(envelope["iv"]), base64.b64decode(envelope["data"]), None
    )


def credentials(settings: Settings) -> tuple[str, str] | None:
    if not settings.po_user or settings.po_password is None:
        return None
    password = settings.po_password.get_secret_value()
    return (settings.po_user, password) if password else None


def run(src: Path, dst: Path, settings: Settings, iterations: int = KDF_ITERATIONS) -> bool:
    """Encrypt `src` into `dst`, always remove `src`. Returns whether `dst` was written."""
    plaintext = src.read_bytes()
    src.unlink()
    dst.unlink(missing_ok=True)
    creds = credentials(settings)
    if creds is None:
        print(
            "PO credentials not set (VNSTRATLAB_PO_USER / VNSTRATLAB_PO_PASSWORD): "
            "dashboard data not published."
        )
        return False
    dst.write_text(json.dumps(encrypt(plaintext, *creds, iterations=iterations)), encoding="utf-8")
    print(f"PO dashboard data encrypted -> {dst}")
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--in", dest="src", type=Path, required=True)
    p.add_argument("--out", dest="dst", type=Path, required=True)
    args = p.parse_args(argv)
    if not args.src.is_file():
        print(f"input not found: {args.src}", file=sys.stderr)
        return 1
    run(args.src, args.dst, load_settings())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
