import re

with open(r'C:\Users\cgrub\OneDrive\Documents\apus_mab\backups\mapus_interventoria_20260914_111409.sql', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    
    # Find all CREATE TABLE statements
    creates = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+) \(', content)
    print("Tables found:", set(creates))
    
    # Find all INSERT statements (any table)
    inserts = re.findall(r'INSERT INTO `.+?` VALUES \(.*?\);', content, re.DOTALL)
    print(f"Total INSERT statements: {len(inserts)}")
    
    # Show first few inserts
    for i, insert in enumerate(inserts[:3]):
        print(f'\nInsert {i+1}:')
        print(insert[:300])
    
    # Look for apus-related content with REFERENCIA
    apus_ref = re.findall(r'.apus.+?REFERENCIA', content, re.IGNORECASE | re.DOTALL)
    print(f'\napus + REFERENCIA matches: {len(apus_ref)}')
    
    # Sample
    for r in apus_ref[:3]:
        print(f'  {r[:200]}')