"""Genera las claves VAPID para Web Push. Uso: python scripts/gen_vapid.py <carpeta_de_datos>"""
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from py_vapid.utils import b64urlencode

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
out.mkdir(parents=True, exist_ok=True)
pem = out / "vapid_private.pem"
if pem.exists():
    sys.exit(f"Ya existe {pem}; bórralo si quieres generar otra clave.")
vapid = Vapid01()
vapid.generate_keys()
vapid.save_key(str(pem))
raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
print(f"Clave privada guardada en {pem}")
print(f"VAPID_PUBLIC_KEY={b64urlencode(raw)}")
