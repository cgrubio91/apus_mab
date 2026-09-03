import openpyxl

wb = openpyxl.load_workbook('scratch/idu_2026.xlsx', read_only=True)

for target in ['APU', 'Inusmos']:
    print(f"\n==================== SHEET: {target} ====================")
    ws = wb[target]
    row_num = 0
    for row in ws.iter_rows(values_only=True):
        if any(row):
            row_num += 1
            non_empty = [str(c) for c in row if c is not None]
            if row_num <= 10:
                print(f"Row {row_num}:", " | ".join(non_empty[:10]))
            if row_num > 15:
                break
    print(f"Total sample rows inspected: {row_num}")
