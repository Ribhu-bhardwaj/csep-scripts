import pdfplumber
with pdfplumber.open("/mnt/c/Users/ribhu/Downloads/Report on Performance of Power Utilities 2024-25.pdf") as pdf:
    # find the right page first — check a few around the revenue structure pages
    for idx in range(18,22):
        text = pdf.pages[idx].extract_text()
        if text and "Energy Sold" in text:
            print(f"Found on index {idx}")
            for i, line in enumerate(text.split('\n')):
                print(i, repr(line))
            break