import requests, json, re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
r = requests.get("https://www.homecenter.com.co/homecenter-co/search?Ntt=cemento", headers=headers, timeout=10)
data = json.loads(re.findall(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)[0])
search_data = data["props"]["pageProps"]["searchProps"]["searchData"]
print("searchData keys:", search_data.keys())
products = search_data.get("results", [])
print(f"Products count: {len(products)}")
for p in products[:3]:
    print("DisplayName:", p.get("displayName"))
    print("Price:", p.get("prices"))
    print("Brand:", p.get("brand"))
    print("URL:", p.get("url"))
    print("---")
