#!/usr/bin/env python
"""Extract apus table CREATE and sample data from backup."""
import re

filepath = r'C:\Users\cgrub\OneDrive\Documents\apus_mab\backups\aiven_backup_20260722.sql'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Find apus table CREATE
apus_create = re.search(
    r'CREATE TABLE IF NOT EXISTS apus \(.*?\);',
    content,
    re.DOTALL
)
if apus_create:
    print("apus table CREATE:")
    print(apus_create.group()[:3000])

# Find all INSERT INTO apus statements
inserts = re.findall(
    r"INSERT INTO `apus` VALUES \(.*?\);",
    content,
    re.DOTALL
)
print(f"\nTotal INSERT INTO apus: {len(inserts)}")

# Show first 5 inserts
for i, insert in enumerate(inserts[:5]):
    print(f"\nInsert {i+1}:")
    print(insert[:200])

# Count how many have 'REFERENCIA' in the origen position (column index 16 based on earlier inspection)
# Let's check column positions by looking at one insert in detail
print("\n\nDetailed analysis of first insert:")
first = inserts[0]
# Remove the INSERT INTO and VALUES parts
values_match = re.search(r'VALUES \((.*?)\);', first)
if values_match:
    values_str = values_match.group(1)
    # Split by comma, but be careful with quoted strings
    # Simple approach: count occurrences of 'REFERENCIA'
    referencia_count = values_str.count('REFERENCIA')
    print(f"REFERENCIA count in first insert: {referencia_count}")
    
    # Let's just print the values string trimmed
    print(f"Values ({len(values_str)} chars): {values_str[:300]}")