def categorize_item(name: str) -> str:
    name = name.lower()
    if "хліб" in name or "булк" in name:
        return "Хліб"
    elif "вода" in name or "напій" in name:
        return "Напої"
    elif "сигарет" in name or "пар" in name:
        return "Сигарети"
    elif "томат" in name or "помідор" in name:
        return "Овочі"
    return "Інше"

