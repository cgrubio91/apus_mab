import requests
import re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
r = requests.get('https://www.idu.gov.co/page/siipviales/economico/portafolio', headers=headers, timeout=10)
html = r.text

# Find links to xls, xlsx, pdf, zip or iframes
links = re.findall(r'href="([^"]+)"', html)
print(f"Total links: {len(links)}")
interesting = [l for l in links if any(ext in l.lower() for ext in ['.xls', '.xlsx', '.pdf', '.zip', 'precio', 'siip', 'visor', 'descarga'])]
print("Interesting links:")
for l in list(set(interesting))[:20]:
    print("  ", l)

# Find iframes
iframes = re.findall(r'<iframe[^>]*src="([^"]+)"', html)
print("\nIframes:")
for f in iframes:
    print("  ", f)

# Find text blocks with 'precio' or 'descargar'
matches = re.findall(r'>([^<]*(?:precio|tarifa|unitario|descarg)[^<]*)<', html, re.I)
print("\nText snippets:")
for m in list(set([m.strip() for m in matches if len(m.strip()) > 10]))[:10]:
    print("  *", m)
