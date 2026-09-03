import requests
import json
import re

def buscar_cype(query):
    url = f"https://coregpaccount.cype.com/api/search?q={requests.utils.quote(query)}&zone=6&offset=0&limit=3&lang_interface=es"
    try:
        res = requests.get(url, timeout=6).json()
        return res.get("records", [])
    except Exception as e:
        print("Error CYPE:", e)
        return []

def buscar_homecenter(query):
    url = f"https://www.homecenter.com.co/homecenter-co/search?Ntt={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url, headers=headers, timeout=6)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
        if m:
            data = json.loads(m.group(1))
            res = data.get("props", {}).get("pageProps", {}).get("searchProps", {}).get("searchData", {}).get("results", [])
            items = []
            for p in res[:3]:
                prices = p.get("prices", [{}])
                raw_price = prices[0].get("priceWithoutFormatting") if prices else None
                items.append({
                    "nombre": p.get("displayName"),
                    "precio": raw_price,
                    "marca": p.get("brand"),
                })
            return items
    except Exception as e:
        print("Error Homecenter:", e)
    return []

print("=== 1. Concreto 3000 PSI ===")
cype_concreto = buscar_cype("concreto f'c=210")
print("CYPE:", [(r['code'], r['title']) for r in cype_concreto[:2]])

print("\n=== 2. Acero de refuerzo ===")
cype_acero = buscar_cype("acero barras corrugadas")
print("CYPE:", [(r['code'], r['title']) for r in cype_acero[:2]])
hc_acero = buscar_homecenter("varilla corrugada")
print("Homecenter:", hc_acero[:2])

print("\n=== 3. Madera encofrado ===")
hc_madera = buscar_homecenter("tabla madera pino construccion")
print("Homecenter:", hc_madera[:2])

print("\n=== 4. Mano de obra (Cuadrilla) ===")
cype_mo = buscar_cype("oficial concreto armado")
print("CYPE:", [(r['code'], r['title']) for r in cype_mo[:2]])
