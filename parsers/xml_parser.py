def parse_format_atb(root):
    items = []

    # Крок 1: збираємо знижки у словник
    discounts = {}
    for d in root.xpath(".//D"):
        item_num = d.attrib.get("NI")
        discount = int(d.attrib.get("SM", "0"))
        if item_num:
            discounts[item_num] = discount

    # Крок 2: проходимось по товарах
    for p in root.xpath(".//P"):
        name = p.attrib.get("NM", "Невідомо")
        summ = int(p.attrib.get("SM", "0"))
        item_num = p.attrib.get("N")
        discount = discounts.get(item_num, 0)
        final_sum = max(summ - discount, 0)  # щоб не було від’ємного значення
        date = extract_timestamp(root)

        items.append({
            "name": name,
            "sum": final_sum,
            "date": date,
            "category": categorize(name)
        })

    return items
