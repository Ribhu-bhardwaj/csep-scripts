import pdfplumber
import pandas as pd
import re

# ================================================================
# CHANGE ZONE 1
# ================================================================
PDF_PATH = "/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf"
PAGE_INDICES = [85,86]  # TODO: fill in (PDF page number - 1 for each page)
OUTPUT_PATH = "/mnt/c/Users/ribhu/csep/AT&C Losses/atc_losses_2022-23.csv"

YEAR_OF_PUBLISHING = "Feb 2026"
YEAR_OF_DATA = "2022-23"
ANNEXURE = "1.8"
TABLE_HEADER = "AT&C Losses"

# ================================================================
# CHANGE ZONE 2
# ================================================================
COLUMNS = [
    "Net_Input_Energy",
    "Net_Energy_Sold",
    "Billing_Efficiency",
    "Collection_Efficiency",
    "ATC_Loss",
]

UNITS = [
    "MU",
    "MU",
    "%",
    "%",
    "%",
]

NUM_COLS = 5

# ================================================================
# CHANGE ZONE 3 — VERSION B (has decimals — % columns)
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

# Andaman & Nicobar PD and Arunachal PD are utility-level rows
# but don't match standard suffixes — handle explicitly
EXPLICIT_UTILITIES = [
    "Andaman & Nicobar PD",
    "Arunachal PD",
]

EXPLICIT_UTILITY_PARENT = {
    "Andaman & Nicobar PD": "Andaman & Nicobar Islands",
    "Arunachal PD":         "Arunachal Pradesh",
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
        'AT&C Losses',
        'AT&C Loss',
        'Net Input Energy',
        'Net Energy Sold',
        'Billing Efficiency',
        'Collection Efficiency',
        '(MU)',
        '(%)',
        'As on March 31',
        'Annexure 1.8',
        'Section 1',
        'Performance of Distribution',
        '2024-25',
        'Dadra & Nagar Haveli and',
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
        elif name in EXPLICIT_UTILITIES:
            row_type = 'utility'
        else:
            row_type = 'utility'

        if row_type in ('state_aggregate', 'grand_total'):
            current_state = name

        # resolve parent state
        if name in EXPLICIT_UTILITY_PARENT:
            parent = EXPLICIT_UTILITY_PARENT[name]
        elif row_type == 'utility':
            parent = current_state
        else:
            parent = name

        for j, col in enumerate(COLUMNS):
            records.append({
                'yop': YEAR_OF_PUBLISHING,
                'yod': YEAR_OF_DATA,
                'ann': ANNEXURE,
                'header': TABLE_HEADER,
                'st': parent,
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
print(f"Total lines extracted: {len(lines)}")

records = parse(lines)

for rec in records:
    if "Puducherry" in rec['dc']:
        rec['st'] = "Puducherry"

df = pd.DataFrame(records)

print("\n--- SAMPLE OUTPUT PREVIEW ---")
print(df.head(20))  # 5 cols * 4 rows
print(f"\nTotal metric rows: {len(df)}")
print(f"Unique Entities (dc): {df['dc'].nunique()}")

df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"\nSuccessfully saved to {OUTPUT_PATH}")