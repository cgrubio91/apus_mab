import openpyxl

wb = openpyxl.load_workbook('scratch/idu_2026.xlsx', read_only=True, data_only=True)
ws = wb["APU"]
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i < 10:
        print(f"Row {i}: len={len(row)}")
        print("  Row values:", [str(c)[:30] for c in row[:8]])
        if i >= 6:
            codigo = row[3]
            nombre = row[4]
            valor = row[6]
            print(f"  Types: cod={type(codigo)}, nom={type(nombre)}, val={type(valor)}")
