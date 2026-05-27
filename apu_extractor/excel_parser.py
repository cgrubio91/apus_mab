"""
📊 Excel Parser Module
Reads Excel files (.xlsx, .xls) and converts sheets into formatted text/markdown for Gemini processing
or directly parses tabular rows if they match expected structures.
"""

import os
import pandas as pd

def extract_text_from_excel(excel_path: str) -> str:
    """
    Reads an Excel file and converts all sheets into structured markdown text.
    This preserves the layout and values so Gemini can parse it accurately.
    
    Args:
        excel_path (str): Absolute path to the Excel file.
        
    Returns:
        str: Text representation of all sheets in markdown format.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at: {excel_path}")
        
    try:
        # Load excel file
        xl = pd.ExcelFile(excel_path)
        sheets_content = []
        
        for sheet_name in xl.sheet_names:
            # Read sheet (do not assume headers initially to capture everything)
            df = xl.parse(sheet_name, header=None)
            
            # Remove completely empty rows and columns
            df = df.dropna(how='all').dropna(axis=1, how='all')
            
            if df.empty:
                continue
                
            sheets_content.append(f"### HOJA: {sheet_name} ###")
            
            # Convert to markdown table format
            # Using custom string conversion to represent cells nicely
            rows = []
            for _, row in df.iterrows():
                row_str = " | ".join([str(val).strip() if pd.notna(val) else "" for val in row])
                rows.append(row_str)
                
            sheets_content.append("\n".join(rows))
            
        return "\n\n".join(sheets_content)
        
    except Exception as e:
        raise Exception(f"Failed to parse Excel file: {e}")

def excel_to_dataframe_dict(excel_path: str) -> dict:
    """
    Converts Excel sheets into a dictionary of pandas DataFrames.
    Useful if a sheet is already fully structured and can be parsed programmatically.
    
    Args:
        excel_path (str): Absolute path to the Excel file.
        
    Returns:
        dict: Keys are sheet names, values are pandas DataFrames.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at: {excel_path}")
        
    try:
        return pd.read_excel(excel_path, sheet_name=None)
    except Exception as e:
        raise Exception(f"Failed to read Excel file into DataFrames: {e}")


BATCH_SIZE = 200


def extract_text_from_excel_batched(excel_path: str):
    """
    Reads an Excel file and yields text chunks (batches of rows) one at a time.
    Each chunk is a small enough to fit in the AI context window.

    Yields:
        tuple[str, str]: (sheet_name, text_chunk)
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at: {excel_path}")

    xl = pd.ExcelFile(excel_path)
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name, header=None)
        df = df.dropna(how='all').dropna(axis=1, how='all')
        if df.empty:
            continue

        rows = []
        for _, row in df.iterrows():
            row_str = " | ".join([str(val).strip() if pd.notna(val) else "" for val in row])
            rows.append(row_str)

        for start in range(0, len(rows), BATCH_SIZE):
            chunk = rows[start:start + BATCH_SIZE]
            text = f"### HOJA: {sheet_name} (filas {start+1}-{start+len(chunk)}) ###\n" + "\n".join(chunk)
            yield sheet_name, text


if __name__ == "__main__":
    # Test script if executed directly
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"📊 Testing Excel extraction on: {test_path}")
        try:
            txt = extract_text_from_excel(test_path)
            print(f"✅ Success. Extracted {len(txt)} chars.")
            print("\nPreview of first 500 chars:")
            print("-" * 40)
            print(txt[:500])
            print("-" * 40)
        except Exception as err:
            print(f"❌ Error: {err}")
    else:
        print("💡 Usage: python excel_parser.py <path_to_excel>")
