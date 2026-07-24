# Imágenes del login (originales)

Coloca aquí las fotos originales (sin optimizar) y el logo. El script de
optimización las convertirá a WebP livianas dentro de `public/login/`.

## Qué archivos dejar aquí

- `slide1.jpg`, `slide2.jpg`, `slide3.jpg`, `slide4.jpg` → las fotos del carrusel
  (puentes, aeropuerto, etc.). Pueden ser `.jpg`, `.jpeg` o `.png`.
- `logo.png` → el logo de MAB (idealmente PNG con fondo transparente).

El orden del carrusel sigue el orden alfabético de los nombres (slide1, slide2…).

## Cómo optimizar

Desde la raíz del proyecto:

```bash
pip install pillow            # solo la primera vez
python scripts/optimizar_login_imagenes.py
```

Esto genera:
- `public/login/slide1.webp` … `slideN.webp`  (máx 1600 px de ancho, ~150–250 KB c/u)
- `public/mab-logo.png`                         (logo redimensionado)

El login ya apunta a esos archivos; al recargar se ven las fotos.
Mientras no estén, el carrusel muestra degradados de respaldo con los colores MAB.
