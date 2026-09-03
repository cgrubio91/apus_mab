import re
from bs4 import BeautifulSoup # Let's see if bs4 is installed or use regex

html = open('scratch/cype_detail.html', encoding='utf-8').read()

# Look for table or breakdown container
tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
print(f"Total tables: {len(tables)}")

for idx, t in enumerate(tables):
    print(f"\n--- Table {idx} ---")
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.DOTALL)
    print(f"Rows: {len(rows)}")
    for r in rows[:6]:
        # Strip tags
        clean_row = " | ".join(re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.DOTALL))
        clean_text = re.sub(r'<[^>]+>', '', clean_row).strip()
        clean_text = re.sub(r'\s+', ' ', clean_text)
        print("  Row:", clean_text[:120])

# Also look for unit and price
unit_match = re.findall(r'(\d+[\d\.,]*)\s*COP', html)
print("\nCOP matches sample:", unit_match[:10])

title_match = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
print("H1 title:", [re.sub(r'<[^>]+>', '', t).strip() for t in title_match])
