
import re

def parse_receipt_text(text):
    lines = text.split('\n')
    items = []
    for line in lines:
        match = re.match(r"(.*?)(\d+[.,]?\d*)\s?(грн|UAH)?", line.strip())
        if match:
            name = match.group(1).strip()
            try:
                price = float(match.group(2).replace(",", "."))
            except ValueError:
                continue
            category = categorize(name)
            items.append((name, price, category))
    return items

def categorize(name):
    name = name.lower()
    if "хліб" in name: return "Хліб"
    if "вода" in name: return "Вода"
    if "сигарет" in name: return "Сигарети"
    if "помідор" in name or "томат" in name: return "Овочі"
    return "Інше"
