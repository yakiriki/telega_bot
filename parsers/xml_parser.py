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
    all_tags = root.xpath(".//P | .//D")  # усі позиції: товари (P) і знижки (D)
    date = extract_timestamp(root)

    current_discount = 0

    for tag in all_tags:
        if tag.tag == "D":
            # знижка застосовується до попереднього товару
            sm = int(tag.attrib.get("SM", "0"))
            current_discount += sm
        elif tag.tag == "P":
            name = tag.attrib.get("NM", "Невідомо").strip()
            summ = int(tag.attrib.get("SM", "0"))
            final_sum = summ - current_discount
            current_discount = 0  # скидаємо після застосування

            items.append({
                "name": name,
                "sum": max(final_sum, 0),
                "date": date,
                "category": categorize(name)
            })

    return items

def parse_format_tax(root):
    items = []
    for row in root.xpath(".//CHECKBODY/ROW"):
        name = row.findtext("NAME", "Невідомо").strip()
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
    return datetime.now().strft
