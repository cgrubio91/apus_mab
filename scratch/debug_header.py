import openpyxl

wb = openpyxl.load_workbook('scratch/idu_2026.xlsx', read_only=True, data_only=True)
for sheet in ['APU', 'Inusmos']:
    ws = wb[sheet]
    print(f"\nSearching header in {sheet}:")
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        str_row = [str(c) for c in row if c is not None]
        if any("Código" in s or "Codigo" in s for s in str_row) and any("Nombre" in s for s in str_row):
            print(f"Header at absolute row {i}:")
            for col_idx, val in enumerate(row):
                if val is not None:
                    print(f"  Col {col_idx}: {val}")
            # print next row (first data row)
            break
