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
    items = []
    date = extract_timestamp(root)

    # Крок 1: зібрати всі товари (елементи P) з індексацією по N
    raw_items = {}
    for p in root.xpath(".//P"):
        index = p.attrib.get("N")
        if not index:
            continue
        name = p.attrib.get("NM", "Невідомо")
        summ = int(p.attrib.get("SM", "0"))
        raw_items[index] = {
            "name": name,
            "sum": summ,
            "date": date,
            "category": categorize(name)
        }

    # Крок 2: знайти всі знижки (елементи D) і застосувати
    for d in root.xpath(".//D"):
        ni = d.attrib.get("NI")  # номер елемента P
        discount = int(d.attrib.get("SM", "0"))
        if ni in raw_items:
            raw_items[ni]["sum"] -= discount
            if raw_items[ni]["sum"] < 0:
                raw_items[ni]["sum"] = 0

    # Крок 3: сформувати результат
    items = list(raw_items.values())
    return items

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
    ts = r
