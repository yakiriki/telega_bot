import requests
from lxml import etree
from io import BytesIO
from datetime import datetime
from utils.categories import categorize

def parse_xml_file(file_path):
    with open(file_path, "rb") as f:
        return parse_xml_bytes(f.read())

def parse_xml_string(text):
    return parse_xml_bytes(text.encode("utf-8"))

def parse_xml_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return parse_xml_bytes(response.content)
    except:
        return []

def parse_xml_bytes(content):
    try:
        tree = etree.parse(BytesIO(content))
        root = tree.getroot()
    except Exception:
        return []

    if root.tag == "RQ":
        return parse_format_atb(root)
    elif root.tag == "CHECK":
        return parse_format_tax(root)
    else:
        return []

def parse_format_atb(root):
    # Сначала собираем товары в словарь по номеру N
    items_dict = {}
    for p in root.xpath(".//P"):
        n = p.attrib.get("N")
        name = p.attrib.get("NM", "Невідомо")
        summ = int(p.attrib.get("SM", "0"))
        date = extract_timestamp(root)
        items_dict[n] = {
            "name": name,
            "sum": summ,
            "date": date,
            "category": categorize(name)
        }

    # Теперь применяем скидки из элементов D по NI (номер товара)
    for d in root.xpath(".//D"):
        ni = d.attrib.get("NI")
        discount = int(d.attrib.get("SM", "0"))
        if ni in items_dict:
            items_dict[ni]["sum"] -= discount

    # Превращаем словарь обратно в список
    return list(items_dict.values())

def parse_format_tax(root):
    items = []
    for row in root.xpath(".//CHECKBODY/ROW"):
        name = row.findtext("NAME", "Невідомо")
        summ = float(row.findtext("COST", "0")) * 100
        date_raw = root.findtext(".//ORDERDATE", "")
        date = format_date(date_raw)
        items.append({
            "name": name,
            "sum": int(summ),
            "date": date,
            "category": categorize(name)
        })
    return items

def extract_timestamp(root):
    ts = root.xpath(".//TS")
    if ts:
        raw = ts[0].text
        try:
            return datetime.strptime(raw, "%Y%m%d%H%M%S").strftime("%Y-%m-%d")
        except:
            pass
    return datetime.now().strftime("%Y-%m-%d")

def format_date(date_raw):
    try:
        return datetime.strptime(date_raw, "%d%m%Y").strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d")
