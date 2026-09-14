#!/usr/bin/env python
"""Check the backup SQL file structure."""
import re
import os

# Read the first backup file
filepath = r'C:\Users\cgrub\OneDrive\Documents\apus_mab\backups\aiven_backup_20260722.sql'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Find CREATE TABLE statements
create_tables = re.findall(
    r'CREATE TABLE IF NOT EXISTS (\w+)',
    content
)
print("Tables found:", set(create_tables))

# Find apus table structure
apus_match = re.search(
    r'CREATE TABLE IF NOT EXISTS apus \(.*?\);',
    content,
    re.DOTALL
)
if apus_match:
    print("\napus table CREATE statement:")
    print(apus_match.group()[:3000])
else:
    print("\napus table not found in first lines")

# Search for "origen" or "referencia" in the file
origen_count = content.count('origen')
referencia_count = content.count('referencia')
print(f"\noccurrences of 'origen': {origen_count}")
print(f"occurrences of 'referencia': {referencia_count}")

# Show lines with "origen" or "referencia"
lines = content.split('\n')
for i, line in enumerate(lines[:500]):
    lower = line.lower()
    if 'origen' in lower or 'referencia' in lower:
        print(f"Line {i+1}: {line[:200]}")