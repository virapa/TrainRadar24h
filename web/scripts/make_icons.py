"""Genera los iconos PNG de la PWA. Uso: python scripts/make_icons.py (desde web/). Requiere Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "public"
BACKGROUND = (16, 21, 28, 255)
ARROW = (224, 69, 123, 255)


def make(size: int) -> None:
    img = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(img)
    s = size / 64  # el dibujo está pensado en una rejilla de 64 con margen para máscaras
    points = [(32, 14), (46, 50), (32, 42), (18, 50)]
    draw.polygon([(x * s, y * s) for x, y in points], fill=ARROW, outline=(255, 255, 255, 255), width=max(1, round(2 * s)))
    img.save(OUT / f"icon-{size}.png")


for px in (192, 512):
    make(px)
print("Iconos generados en", OUT)
