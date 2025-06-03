def categorize_item(name: str) -> str:
    name = name.lower()
    if "хліб" in name: return "Хліб"
    if "вода" in name: return "Вода"
    if "молоко" in name: return "Молочне"
    if "пиво" in name: return "Алкоголь"
    if "сигарет" in name: return "Сигарети"
    return "Інше"
