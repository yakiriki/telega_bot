def parse_xml(root):
    items = []
    total = 0
    receipt_id = root.findtext(".//UID") or "unknown"
    for row in root.findall(".//CHECKBODY/ROW"):
        name = row.findtext("NAME", default="").strip()
        price = float(row.findtext("COST", "0").strip())
        items.append((name, price))
        total += price
    return items, total, receipt_id
