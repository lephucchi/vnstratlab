"""Encrypt the PO dashboard data before it is published (Pages build).

GitHub Pages is static and public, so a login form alone protects nothing. Instead the
dashboard data is published only as an AES-256-GCM envelope whose key is derived with
PBKDF2-HMAC-SHA256 from the PO user name and password. The browser derives the same key
from what the user types (WebCrypto) and can only decrypt with the right credentials.

Threat model: the envelope is public, so anyone can try passwords offline. 600k PBKDF2
iterations slow that down, but protection rests on the password: use a random one of 16+
characters. The data itself is assembled from public repository and GitHub API content;
encryption hides the dashboard view, not confidential facts.

Credentials come only from `vnstratlab.settings.Settings`: PO_USERNAME and PO_PASSWORD
(environment / `.env`; GitHub secrets in CI). They are never printed or written anywhere.
Both are NFC-normalised and stripped of surrounding whitespace, exactly as the PO page does
with what the user types, so a secret saved with a trailing newline still works.

`tools/build_status.py` calls `publish()` directly, so plaintext PO data is never written,
whichever version of pages.yml runs. Without credentials nothing is published under /po/.

Usage (re-encrypt an existing file):
  python tools/encrypt_po.py --in _site/po/data.json --out _site/po/data.enc.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vnstratlab.settings import Settings, load_settings

ENVELOPE_VERSION = 1
ALG = "AES-256-GCM"
KDF = "PBKDF2-SHA256"
KDF_ITERATIONS = 600_000
SALT_BYTES = 16
IV_BYTES = 12
ENC_NAME = "data.enc.json"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def normalise(value: str) -> str:
    """Same rule as the PO page: Unicode NFC, surrounding whitespace removed."""
    return unicodedata.normalize("NFC", value).strip()


def key_material(user: str, password: str) -> bytes:
    """What both sides feed to PBKDF2: normalised user and password joined by a newline."""
    return f"{normalise(user)}\n{normalise(password)}".encode()


def derive_key(user: str, password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", key_material(user, password), salt, iterations, dklen=32)


def encrypt(
    plaintext: bytes,
    user: str,
    password: str,
    iterations: int = KDF_ITERATIONS,
    *,
    salt: bytes | None = None,
    iv: bytes | None = None,
) -> dict[str, Any]:
    """Build the envelope. `salt`/`iv` are random unless given (test vectors only)."""
    salt = salt if salt is not None else os.urandom(SALT_BYTES)
    iv = iv if iv is not None else os.urandom(IV_BYTES)
    key = derive_key(user, password, salt, iterations)
    return {
        "v": ENVELOPE_VERSION,
        "alg": ALG,
        "kdf": KDF,
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
    user = normalise(settings.po_username or "")
    password = normalise(settings.po_password.get_secret_value()) if settings.po_password else ""
    return (user, password) if user and password else None


def publish(
    plaintext: bytes, po_dir: Path, settings: Settings, iterations: int = KDF_ITERATIONS
) -> bool:
    """Write `<po_dir>/data.enc.json`, or nothing without credentials. Never plaintext."""
    dst = po_dir / ENC_NAME
    dst.unlink(missing_ok=True)
    creds = credentials(settings)
    if creds is None:
        # GitHub Actions annotation, visible in the run summary
        print("::warning::PO_USERNAME / PO_PASSWORD not set: PO dashboard data not published.")
        return False
    po_dir.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(encrypt(plaintext, *creds, iterations=iterations)), encoding="utf-8")
    print(f"PO dashboard data encrypted -> {dst}")
    return True


def run(src: Path, dst: Path, settings: Settings, iterations: int = KDF_ITERATIONS) -> bool:
    """Encrypt `src` into `dst`, always remove `src`. Returns whether `dst` was written."""
    plaintext = src.read_bytes()
    src.unlink()
    dst.unlink(missing_ok=True)
    written = publish(plaintext, dst.parent, settings, iterations)
    if written and dst.name != ENC_NAME:
        (dst.parent / ENC_NAME).replace(dst)
    return written


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
