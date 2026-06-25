import pdfplumber
import pandas as pd
import re

# ================================================================
# CHANGE ZONE 1
# ================================================================
PDF_PATH = "/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf"
PAGE_INDICES = [35, 36] # Update these if the page numbers differ in your PDF
OUTPUT_PATH = "/mnt/c/Users/ribhu/csep/Cost Structure/cost_structure_2022-23.csv"

YEAR_OF_PUBLISHING = "Feb 2026"
YEAR_OF_DATA = "2023-24"
ANNEXURE = "1.2 (a)"
TABLE_HEADER = "Cost Structure"

# ================================================================
# CHANGE ZONE 2
# ================================================================
COLUMNS = [
    "gross_input_energy",
    "cost_of_power_including_own_generation",
    "employee_cost",
    "interest_cost",
    "depreciation",
    "other_costs",
    "ACS"
]

# First column is in MU, the rest are in Rs/kWh
UNITS = ["MU"] + ["Rs/kWh"] * 6

NUM_COLS = 7

# ================================================================
# CHANGE ZONE 3 — VERSION B (With Decimals for Rs/kWh)
# ================================================================
# Added '.' inside the character sets to properly match decimal numbers
TOKEN_RE = re.compile(r'\([\d,.]+\)|[\d,.]+|-(?=\s|$)')

# ================================================================
# NEVER TOUCH BELOW THIS LINE
# ================================================================

STATE_NAMES = [
    "State Sector", "Andaman & Nicobar Islands", "Andhra Pradesh",
    "Arunachal Pradesh", "Assam", "Bihar", "Chattisgarh", "Delhi",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Daman & Diu", "Private Sector", "Grand Total"
]

def clean_number(s):
    if s is None:
        return None
    s = str(s).strip()
    if s in ['-', '', 'None', 'null']:
        return None
    negative = s.startswith('(') and s.endswith(')')
    s = s.replace('(', '').replace(')', '').replace(',', '').replace(' ', '')
    try:
        val = float(s)
        return -val if negative else val
    except:
        return None

def extract_lines(pdf_path, page_indices):
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx in page_indices:
            page = pdf.pages[idx]
            text = page.extract_text()
            if text:
                all_lines.extend(text.split('\n'))
    return all_lines

def get_values(raw_tokens):
    tokens = list(raw_tokens)
    max_iter = 5
    for _ in range(max_iter):
        if len(tokens) <= NUM_COLS:
            break
        merged = False
        for i in range(len(tokens) - 1):
            t = tokens[i]
            next_t = tokens[i + 1]
            if (re.match(r'^\d{1,3}$', t) and
                re.match(r'^[,\d]', next_t) and
                ',' in next_t and
                next_t not in ['-']):
                tokens = tokens[:i] + [t + next_t] + tokens[i + 2:]
                merged = True
                break
        if not merged:
            break
    while len(tokens) < NUM_COLS:
        tokens.append(None)
    return tokens[:NUM_COLS]

def parse(lines):
    start_idx = next((i for i, l in enumerate(lines) if 'State Sector' in l), None)
    if start_idx is None:
        print("Could not find State Sector row")
        return []

    data_lines = lines[start_idx:]
    records = []
    current_state = None
    current_sector = 'Public'

    skip_patterns = [
        'Cost Structure',            # table title
        'Rs /kWh',                   # unit note
        'Gross Input',               # header line 1
        'Energy',                    # header line 2
        'Section 1',                 # never changes
        'Annexure',                  # never changes
        '2024-25',                   # data year / footer
        'Dadra & Nagar Haveli and',  # row fragment splitter protection
        'Cost of Power',             
        '(including own',            
        'generation)',               
    ]

    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        if any(p in line for p in skip_patterns):
            continue

        if 'Private Sector' in line:
            current_sector = 'Private'

        token_matches = list(TOKEN_RE.finditer(line))
        if not token_matches:
            continue

        first_pos = token_matches[0].start()
        name = line[:first_pos].strip()
        raw_tokens = [m.group() for m in token_matches]

        if not name:
            continue

        values = get_values(raw_tokens)

        if name == 'Grand Total':
            row_type = 'grand_total'
        elif name in STATE_NAMES:
            row_type = 'state_aggregate'
        else:
            row_type = 'utility'

        if row_type in ('state_aggregate', 'grand_total'):
            current_state = name

        for j, col in enumerate(COLUMNS):
            records.append({
                'yop': YEAR_OF_PUBLISHING,
                'yod': YEAR_OF_DATA,
                'ann': ANNEXURE,
                'header': TABLE_HEADER,
                'st': current_state if row_type == 'utility' else name,
                'dc': name,
                'row_type': row_type,
                'sector': current_sector,
                'label': col,
                'unit': UNITS[j],
                'number': clean_number(values[j]),
                'pg': 1
            })

    return records

# ---- RUN ----
lines = extract_lines(PDF_PATH, PAGE_INDICES)

start_idx = next((i for i, l in enumerate(lines) if 'State Sector' in l), None)
print(f"Start index found: {start_idx}")
print(f"Total lines: {len(lines)}")

records = parse(lines)
df = pd.DataFrame(records)

print(df.head(21)) # Printing top 21 rows to easily see the full breakdown of first 3 entities
print(f"\nTotal rows: {len(df)}")
print(f"Unique DISCOMs: {df['dc'].nunique()}")
print(f"Nulls in number: {df['number'].isna().sum()}")
print(f"\nSector breakdown:\n{df[['dc','sector']].drop_duplicates()['sector'].value_counts()}")
print(f"\nLast entity: {df['dc'].iloc[-1] if len(df) > 0 else 'EMPTY'}")

df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"\nSaved to {OUTPUT_PATH}")