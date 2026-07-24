"""Optimiza las imágenes del login MAB.

Lee los originales de  frontend/public/login/_originales/  y genera:
  - frontend/public/login/slideN.webp   (fotos del carrusel, WebP livianas)
  - frontend/public/mab-logo.png        (logo redimensionado, conserva transparencia)

Uso:
    pip install pillow
    python scripts/optimizar_login_imagenes.py
"""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Falta Pillow. Instálalo con:  pip install pillow")

RAIZ = Path(__file__).resolve().parent.parent
ORIGINALES = RAIZ / "frontend" / "public" / "login" / "_originales"
DESTINO_LOGIN = RAIZ / "frontend" / "public" / "login"
DESTINO_PUBLIC = RAIZ / "frontend" / "public"

SLIDE_ANCHO_MAX = 1600      # px
SLIDE_CALIDAD = 78          # WebP
LOGO_ALTO_MAX = 160         # px

EXT_IMG = {".jpg", ".jpeg", ".png", ".webp"}


def _redimensionar(img: Image.Image, ancho_max: int | None = None, alto_max: int | None = None) -> Image.Image:
    w, h = img.size
    escala = 1.0
    if ancho_max and w > ancho_max:
        escala = min(escala, ancho_max / w)
    if alto_max and h > alto_max:
        escala = min(escala, alto_max / h)
    if escala < 1.0:
        img = img.resize((round(w * escala), round(h * escala)), Image.LANCZOS)
    return img


def optimizar() -> None:
    if not ORIGINALES.exists():
        raise SystemExit(f"No existe la carpeta de originales: {ORIGINALES}")

    archivos = sorted(
        p for p in ORIGINALES.iterdir()
        if p.suffix.lower() in EXT_IMG and p.is_file()
    )
    if not archivos:
        raise SystemExit(f"No hay imágenes en {ORIGINALES}")

    slides = [p for p in archivos if "logo" not in p.stem.lower()]
    logos = [p for p in archivos if "logo" in p.stem.lower()]

    DESTINO_LOGIN.mkdir(parents=True, exist_ok=True)

    for i, ruta in enumerate(slides, start=1):
        img = Image.open(ruta).convert("RGB")
        img = _redimensionar(img, ancho_max=SLIDE_ANCHO_MAX)
        salida = DESTINO_LOGIN / f"slide{i}.webp"
        img.save(salida, "WEBP", quality=SLIDE_CALIDAD, method=6)
        print(f"  slide{i}.webp  <-  {ruta.name}  ({salida.stat().st_size // 1024} KB)")

    for ruta in logos[:1]:
        img = Image.open(ruta).convert("RGBA")
        img = _redimensionar(img, alto_max=LOGO_ALTO_MAX)
        salida = DESTINO_PUBLIC / "mab-logo.png"
        img.save(salida, "PNG", optimize=True)
        print(f"  mab-logo.png  <-  {ruta.name}  ({salida.stat().st_size // 1024} KB)")

    print(f"\nListo: {len(slides)} slide(s) y {min(len(logos), 1)} logo generados.")


if __name__ == "__main__":
    optimizar()
