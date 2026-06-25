import pdfplumber
import pandas as pd
import re

# ---- CONFIG ----
PDF_PATH = "/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf"
PAGE_INDICES = [23, 24]  # add 21 if data still incomplete
OUTPUT_PATH = "/mnt/c/Users/ribhu/csep/Revenue Structure on Energy Sold basis/revenue_structure_energy_sold_2022-23.csv"

YEAR_OF_PUBLISHING = "Feb 2026"
YEAR_OF_DATA = "2022-23"
ANNEXURE = "1.1(b)"
TABLE_HEADER = "Revenue Structure on Energy Sold basis"

COLUMNS = [
    "gross_energy_sold_mu",
    "revenue_from_sale_of_power",
    "other_operating_income_including_wheeling_charges",
    "tariff_subsidy",
    "regulatory_income_and_revenue_grant_under_uday_for_loan_takeover",
    "other_income_and_revenue_grants",
    "arr_on_energy_sold_basis",
    "arr_on_energy_sold_excluding_regulatory_income_and_revenue_grant_under_uday_for_loan_takeover"
]

UNITS = ["MU"] + ["Rs./kWh"] * 7  # 8 total, first is MU rest are Rs./kWh

STATE_NAMES = [
    "State Sector", "Andaman & Nicobar Islands", "Andhra Pradesh",
    "Arunachal Pradesh", "Assam", "Bihar", "Chattisgarh", "Delhi",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Daman & Diu",
    "Private Sector",
    "Grand Total"
]

# Updated TOKEN_RE — handles:
# (0.28) parenthesized negatives
# -0.31  direct negative decimals  ← NEW
# 4.80   positive decimals
# 1,108  comma numbers
# -      standalone dash (missing value)
TOKEN_RE = re.compile(r'\([\d,.]+\)|-[\d,.]+|[\d,.]+|-(?=\s|$)')

# ---- HELPERS ----
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
        return -val if negative else val  # direct negatives like -0.31 handled by float() itself
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
    """
    Target is 8 columns for this table.
    Merges split Indian-format numbers (e.g. '1 13,966' -> '113,966').
    Decimal values won't trigger merging since they have no commas.
    """
    tokens = list(raw_tokens)
    max_iter = 5
    for _ in range(max_iter):
        if len(tokens) <= 8:
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
    while len(tokens) < 8:
        tokens.append(None)
    return tokens[:8]

# ---- PARSE ----
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
        'Revenue Structure on Energy Sold',  # table title
        'Rs./kWh',                           # unit note
        'Section 1',                         # section header
        'Annexure',                          # annexure label
        'ARR on Energy',                     # column header fragment line 4
        'Other Sold excluding',              # column header fragment line 5
        'Operating Regulatory',              # column header fragment line 6
        'Income Income and',                 # column header fragment line 7
        'Gross Energy including',            # column header fragment line 8
        'sold Revenue from',                 # column header fragment line 9
        '(MU) Sale of Power',               # column header fragment line 10
        '2024-25',                           # year row + catches spaced footer
        'Dadra & Nagar Haveli and',          # first line of split state name
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

print(df.head(20))
print(f"\nTotal rows: {len(df)}")
print(f"Unique DISCOMs: {df['dc'].nunique()}")
print(f"Nulls in number: {df['number'].isna().sum()}")
print(f"\nSector breakdown:\n{df[['dc','sector']].drop_duplicates()['sector'].value_counts()}")

# Verify last entity parsed — should be Grand Total
print(f"\nLast entity: {df['dc'].iloc[-1] if len(df) > 0 else 'EMPTY'}")

df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"\nSaved to {OUTPUT_PATH}")