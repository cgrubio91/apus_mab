import requests
import re

r = requests.get("https://colombia.generadordeprecios.info/obra_nueva/", timeout=10)
# Look for scripts that handle search
scripts = re.findall(r'<script[^>]*src="([^"]+)"', r.text)
print("Scripts:")
for s in scripts:
    print(" ", s)

# Look for inline scripts
inline = re.findall(r'<script>(.*?)</script>', r.text, re.DOTALL)
print(f"Inline scripts: {len(inline)}")
for idx, s in enumerate(inline):
    if "search" in s.lower() or "buscar" in s.lower() or "api" in s.lower():
        print(f"--- Inline {idx} ---")
        print(s[:500])

# Check one of the categories like Cimentaciones.html
r2 = requests.get("https://colombia.generadordeprecios.info/obra_nueva/Cimentaciones.html", timeout=10)
print("\nCimentaciones status:", r2.status_code)
links2 = re.findall(r'href="([^"]+)"', r2.text)
ciment_links = [l for l in links2 if "Cimentaciones" in l or ".html" in l]
print("Cimentaciones links sample:", ciment_links[:10])
