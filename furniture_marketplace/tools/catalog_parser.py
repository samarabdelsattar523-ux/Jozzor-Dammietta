# -*- coding: utf-8 -*-
"""Pure-python parser/validator for manufacturer product catalogs (CSV / XLSX).

No Odoo imports on purpose so it can be unit-tested stand-alone.
"""
import csv
import io
import re
import zipfile

from lxml import etree

try:
    from odoo import _
except ImportError:
    def _(s, *args):
        return s % args if args else s

REQUIRED = ('product_name', 'category', 'description', 'price', 'quantity')
OPTIONAL = ('sku', 'image', 'specifications')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
MAX_BYTES = 5 * 1024 * 1024
MAX_UNZIPPED = 50 * 1024 * 1024
ALIASES = {
    'name': 'product_name', 'product': 'product_name', 'title': 'product_name',
    'product_category': 'category', 'categories': 'category',
    'product_description': 'description',
    'selling_price': 'price', 'sale_price': 'price', 'list_price': 'price',
    'available_quantity': 'quantity', 'qty': 'quantity', 'stock': 'quantity',
    'product_image': 'image', 'image_reference': 'image', 'image_url': 'image',
    'product_specifications': 'specifications', 'specs': 'specifications',
    'specification': 'specifications',
    'internal_reference': 'sku', 'default_code': 'sku', 'reference': 'sku', 'code': 'sku',
    'product_code': 'sku', 'item_code': 'sku',
}
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
T_TAG = '{%s}t' % NS


def normalize_header(value):
    key = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')
    return ALIASES.get(key, key)


def _decode(raw):
    for enc in ('utf-8-sig', 'cp1256', 'latin-1'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


def read_csv(raw):
    text = _decode(raw)
    first = (text.splitlines() or [''])[0]
    delimiter = ';' if first.count(';') > first.count(',') else ','
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _col_index(ref):
    letters = re.match(r'[A-Za-z]+', ref or '')
    if not letters:
        return None
    n = 0
    for ch in letters.group().upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _number_to_text(text):
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    return str(int(number)) if number.is_integer() else repr(number)


def read_xlsx(raw):
    zf = zipfile.ZipFile(io.BytesIO(raw))
    if sum(i.file_size for i in zf.infolist()) > MAX_UNZIPPED:
        raise ValueError(_('The spreadsheet is too large once unpacked.'))
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    names = zf.namelist()
    shared = []
    if 'xl/sharedStrings.xml' in names:
        root = etree.fromstring(zf.read('xl/sharedStrings.xml'), parser)
        for si in root.findall('{%s}si' % NS):
            shared.append(''.join(t.text or '' for t in si.iter(T_TAG)))
    sheets = sorted(n for n in names if re.match(r'xl/worksheets/sheet\d+\.xml$', n))
    if not sheets:
        raise ValueError(_('No worksheet found in the file.'))
    sheet = 'xl/worksheets/sheet1.xml' if 'xl/worksheets/sheet1.xml' in names else sheets[0]
    root = etree.fromstring(zf.read(sheet), parser)
    table = []
    for row in root.iter('{%s}row' % NS):
        cells = {}
        next_idx = 0
        for c in row.findall('{%s}c' % NS):
            idx = _col_index(c.get('r'))
            idx = next_idx if idx is None else idx
            next_idx = idx + 1
            ctype = c.get('t')
            if ctype == 'inlineStr':
                val = ''.join(t.text or '' for t in c.iter(T_TAG))
            else:
                v = c.find('{%s}v' % NS)
                val = v.text if v is not None and v.text is not None else ''
                if ctype == 's' and val != '':
                    val = shared[int(val)] if int(val) < len(shared) else ''
                elif ctype in (None, 'n') and val != '':
                    val = _number_to_text(val)
            cells[idx] = val
        width = (max(cells) + 1) if cells else 0
        table.append([cells.get(i, '') for i in range(width)])
    return table


def _to_float(text):
    value = float(str(text).replace(',', '').strip())
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError('invalid number')
    return value


def parse_catalog(filename, raw, max_rows=500):
    """Return (rows, errors).

    rows   -> list of dict(row_no, product_name, category, description, price,
              quantity, image, specifications, errors=[...])
    errors -> flat list of human readable messages (empty list == file is valid)
    """
    errors = []
    fname = (filename or '').lower()
    if not raw:
        return [], [_('The uploaded file is empty.')]
    if len(raw) > MAX_BYTES:
        return [], [_('The file is larger than %d MB.', MAX_BYTES // 1024 // 1024)]
    try:
        if fname.endswith('.csv'):
            table = read_csv(raw)
        elif fname.endswith('.xlsx'):
            table = read_xlsx(raw)
        else:
            return [], [_('Unsupported file type. Please upload a .csv or .xlsx file.')]
    except Exception as exc:  # noqa: BLE001 - any parsing failure is a user error
        return [], [_('The file could not be read (%s). Please use the provided template.', exc)]

    table = [list(r) for r in table]
    while table and not any(str(c).strip() for c in table[0]):
        table.pop(0)
    if not table:
        return [], [_('The file does not contain any data.')]

    headers = [normalize_header(h) for h in table[0]]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        return [], [_('Missing required column(s): %s. Please use the provided template.', ', '.join(missing))]

    rows = []
    seen = {}  # duplicate rows inside the same file: by SKU, otherwise by product name
    for offset, raw_row in enumerate(table[1:], start=2):
        if not any(str(c).strip() for c in raw_row):
            continue
        data = {}
        for i, h in enumerate(headers):
            if h and h not in data:
                data[h] = str(raw_row[i]).strip() if i < len(raw_row) else ''
        row_errors = []
        for col in ('product_name', 'category', 'description'):
            if not data.get(col):
                row_errors.append(_('%s is required.', col.replace('_', ' ').title()))
        price = quantity = 0.0
        try:
            price = _to_float(data.get('price', ''))
            if price < 0:
                row_errors.append(_('Price cannot be negative.'))
        except ValueError:
            row_errors.append(_('Price must be a number (got "%s").', data.get('price', '')))
        try:
            quantity = _to_float(data.get('quantity', ''))
            if quantity < 0:
                row_errors.append(_('Quantity cannot be negative.'))
        except ValueError:
            row_errors.append(_('Quantity must be a number (got "%s").', data.get('quantity', '')))
        key = (data.get('sku') or data.get('product_name') or '').strip().lower()
        if key and key in seen:
            row_errors.append(_('Duplicate of row %d (same SKU or product name).', seen[key]))
        elif key:
            seen[key] = offset
        image = data.get('image', '')
        if image and not (re.match(r'https?://', image, re.I) or image.lower().endswith(IMAGE_EXT)):
            row_errors.append(_('Image must be an http(s) URL or an image file name (%s).', ', '.join(IMAGE_EXT)))
        rows.append({
            'row_no': offset,
            'product_name': data.get('product_name', ''),
            'sku': data.get('sku', ''),
            'category': data.get('category', ''),
            'description': data.get('description', ''),
            'price': price,
            'quantity': quantity,
            'image': image,
            'specifications': data.get('specifications', ''),
            'errors': row_errors,
        })
    if not rows:
        errors.append(_('The file has a header row but no product rows.'))
    if len(rows) > max_rows:
        errors.append(_('The file has %d products; the maximum per upload is %d.', len(rows), max_rows))
    for r in rows:
        errors.extend('Row %d: %s' % (r['row_no'], e) for e in r['errors'])
    return rows, errors
