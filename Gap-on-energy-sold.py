import pdfplumber
import pandas as pd
import re

# ================================================================
# CHANGE ZONE 1
# ================================================================
PDF_PATH = "/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf"
PAGE_INDICES = [49,50]  # TODO: fill in (PDF page number - 1 for each page, both pages)

OUTPUT_PATH_2024 = "/mnt/c/Users/ribhu/csep/Gap on Energy Sold basis/gap_energy_sold_2024-25.csv"
OUTPUT_PATH_2023 = "/mnt/c/Users/ribhu/csep/Gap on Energy Sold basis/gap_energy_sold_2023-24.csv"
OUTPUT_PATH_2022 = "/mnt/c/Users/ribhu/csep/Gap on Energy Sold basis/gap_energy_sold_2022-23.csv"

YEAR_OF_PUBLISHING = "Feb 2026"
ANNEXURE = "1.3(a)"
TABLE_HEADER = "Gap on Energy Sold basis"

# ================================================================
# CHANGE ZONE 2
# 9 cols total = 3 years x 3 metrics
# Order in PDF (left to right): 2024-25 | 2023-24 | 2022-23
# ================================================================
COLUMNS_PER_YEAR = [
    "ACS_on_Energy_Sold_basis",
    "ARR_on_Energy_Sold_excl_Regulatory_Income_and_Revenue_Grant",
    "Gap_on_Energy_Sold_excl_Regulatory_Income_and_Revenue_Grant",
]

YEAR_SLICES = {
    "2024-25(as of March 31,2025)": slice(0, 3),
    "2023-24(as of March 31,2024)": slice(3, 6),
    "2022-23(as of March 31,2023)": slice(6, 9),
}

UNITS_PER_YEAR = ["Rs./kWh", "Rs./kWh", "Rs./kWh"]

NUM_COLS = 9

# ================================================================
# CHANGE ZONE 3 — VERSION B (decimals)
# ================================================================
TOKEN_RE = re.compile(r'\([\d,]+\.?\d*\)|[\d,]+\.?\d*|-(?=\s|$)')

# ================================================================
# NEVER TOUCH BELOW THIS LINE
# ================================================================

STATE_NAMES = [
    "State Sector", "Andaman & Nicobar Island", "Andaman & Nicobar Islands", "Andhra Pradesh",
    "Arunachal Pradesh", "Assam", "Bihar", "Chattisgarh", "Delhi",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Puducherry",
    "Daman & Diu", "Private Sector", "Grand Total"
]

# PD utilities that don't match standard suffixes
EXPLICIT_UTILITY_PARENT = {
    "Andaman & Nicobar PD": "Andaman & Nicobar Islands",
    "Arunachal PD":         "Arunachal Pradesh",
    "Ladakh PD":            "Ladakh",
    "Mizoram PD":           "Mizoram",
    "Nagaland PD":          "Nagaland",
    "Puducherry PD":        "Puducherry",
    "Sikkim PD":            "Sikkim",
}

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
            if idx < len(pdf.pages):
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
        'Gap on Energy Sold',
        'Rs./kWh',
        'ARR on',
        'ACS on',
        'Energy Sold',
        'excluding',
        'Regulatory',
        'Income and',
        'Revenue Grant',
        'under UDAY',
        'for loan',
        'takeover',
        'loan takeover',
        '2024-25',
        '2023-24',
        '2022-23',
        'As on March 31',
        'Annexure 1.3',
        'Section 1',
        'Performance of Distribution',
        'Dadra & Nagar Haveli and',
        'Report on Performance',   # page footer
        'basis',                   # standalone header word
    ]

    seen = set()  # deduplicate rows that appear due to repeated headers on page 2

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

        # skip duplicate entity rows from page-2 header repeat
        if name in seen and name in STATE_NAMES:
            continue

        values = get_values(raw_tokens)

        if name == 'Grand Total':
            row_type = 'grand_total'
        elif name in STATE_NAMES:
            row_type = 'state_aggregate'
        elif name in EXPLICIT_UTILITY_PARENT:
            row_type = 'utility'
        else:
            row_type = 'utility'

        if row_type in ('state_aggregate', 'grand_total'):
            current_state = name
            seen.add(name)

        parent = (
            EXPLICIT_UTILITY_PARENT.get(name)
            or (current_state if row_type == 'utility' else name)
        )

        records.append({
            'name':         name,
            'row_type':     row_type,
            'parent_state': parent,
            'sector':       current_sector,
            'values':       values,
        })

    return records


def build_year_df(records, yod, col_slice):
    rows = []
    for r in records:
        year_vals = r['values'][col_slice]
        for j, col in enumerate(COLUMNS_PER_YEAR):
            rows.append({
                'yop':      YEAR_OF_PUBLISHING,
                'yod':      yod,
                'ann':      ANNEXURE,
                'header':   TABLE_HEADER,
                'st':       r['parent_state'],
                'dc':       r['name'],
                'row_type': r['row_type'],
                'sector':   r['sector'],
                'label':    col,
                'unit':     UNITS_PER_YEAR[j],
                'number':   clean_number(year_vals[j] if j < len(year_vals) else None),
                'pg':       1,
            })
    return pd.DataFrame(rows)


# ---- RUN ----
lines = extract_lines(PDF_PATH, PAGE_INDICES)

start_idx = next((i for i, l in enumerate(lines) if 'State Sector' in l), None)
print(f"Start index found: {start_idx}")
print(f"Total lines extracted: {len(lines)}")

records = parse(lines)
print(f"Parsed entity rows: {len(records)}")

# patch Puducherry
for r in records:
    if "Puducherry" in r['name'] and r['row_type'] == 'utility':
        r['parent_state'] = "Puducherry"

# build 3 dataframes
df_2024 = build_year_df(records, "2024-25(as of March 31,2025)", slice(0, 3))
df_2023 = build_year_df(records, "2023-24(as of March 31,2024)", slice(3, 6))
df_2022 = build_year_df(records, "2022-23(as of March 31,2023)", slice(6, 9))

print("\n--- SAMPLE 2024-25 ---")
print(df_2024.head(12))
print(f"\nEntities in 2024-25: {df_2024['dc'].nunique()}")

df_2024.to_csv(OUTPUT_PATH_2024, index=False, encoding='utf-8-sig')
df_2023.to_csv(OUTPUT_PATH_2023, index=False, encoding='utf-8-sig')
df_2022.to_csv(OUTPUT_PATH_2022, index=False, encoding='utf-8-sig')

print(f"\nSaved:")
print(f"  {OUTPUT_PATH_2024}")
print(f"  {OUTPUT_PATH_2023}")
print(f"  {OUTPUT_PATH_2022}")