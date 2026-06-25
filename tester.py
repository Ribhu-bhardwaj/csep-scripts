import pdfplumber
import pandas as pd
import re

# ---- CONFIG ----
PDF_PATH = "/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf"
PAGE_INDICES = [13, 14]
OUTPUT_PATH = "/mnt/c/Users/ribhu/csep"

YEAR_OF_PUBLISHING = "Feb 2026"
YEAR_OF_DATA = "2024-25"
ANNEXURE = "1.1(a)"
TABLE_HEADER = "Revenue Structure"
UNIT = "Rs crore"

COLUMNS = [
    "revenue_from_operations",
    "tariff_subsidy_billed",
    "regulatory_income",
    "revenue_grant_under_uday_for_loan_takeover",
    "other_income_and_revenue_revenue_grants",
    "total_revenue_on_subsidy_billed_basis",
    "tariff_subsidy_received",
    "total_revenue_on_tariff_subsidy_recieved_excluding_regulatory_income_and_revenue_grant_under_uday_for_loan_takeover"
]

STATE_NAMES = [
    "State Sector", "Andaman & Nicobar Islands", "Andhra Pradesh",
    "Arunachal Pradesh", "Assam", "Bihar", "Chattisgarh", "Delhi",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Daman & Diu",       # fragment of multi-line state name in private sector
    "Private Sector",    # private sector aggregate row
    "Grand Total"        # final total row
]

# Token regex: parenthesized negative | number with commas | standalone dash
TOKEN_RE = re.compile(r'\([\d,]+\)|[\d,]+|-(?=\s|$)')

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
    """
    Merge split numbers iteratively until token count reaches 8.
    Handles cases like '1 0,040' -> '10,040', '1 ,869' -> '1,869', '1 6,892' -> '16,892'
    Logic: if token count > 8, find a short digit-only token whose next token
    contains a comma (meaning it's a fragment of a split number) and merge them.
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
            if (re.match(r'^\d{1,3}$', t) and           # short, no comma = likely fragment
                re.match(r'^[,\d]', next_t) and          # next starts with digit or comma
                ',' in next_t and                         # next has comma = it's a number fragment
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
        'Report on Performance', 'Revenue Details', 'Rs crore',
        'Section 1', 'Annexure', 'Operations Billed', 'Revenue from',
        'Revenue Grant', 'Total Revenue', 'on tariff', 'subsidy',
        'received', 'excluding', 'Regulatory', 'Income and',
        'loan takeover', 'Billed basis', '2024-25',
        'Dadra & Nagar Haveli and'   # first line of split state name — skip, Daman & Diu line handles it
    ]

    for line in data_lines:
        line = line.strip()
        if not line:
            continue
        if any(p in line for p in skip_patterns):
            continue

        # Detect sector switch
        if 'Private Sector' in line:
            current_sector = 'Private'

        # Extract tokens using regex
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
                'unit': UNIT,
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

df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')
print(f"\nSaved to {OUTPUT_PATH}")