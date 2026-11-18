# -*- coding: utf-8 -*-
import base64
import ipaddress
import logging
import os
import socket
import uuid
from urllib.parse import urlparse

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools.catalog_parser import parse_catalog

_logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _is_public_url(url):
    """SSRF guard: only http(s) URLs resolving exclusively to public addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


class FurnitureCatalogImport(models.Model):
    _name = 'furniture.catalog.import'
    _description = 'Product Catalog Upload'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(required=True, default=lambda s: s.env._('Catalog'))
    manufacturer_id = fields.Many2one('furniture.manufacturer', ondelete='cascade', index=True)
    application_id = fields.Many2one('furniture.manufacturer.application', ondelete='cascade', index=True)
    datafile = fields.Binary('File', attachment=True)
    filename = fields.Char()
    state = fields.Selection([('draft', 'Validated - not imported'), ('imported', 'Imported')],
                             default='draft', tracking=True)
    line_ids = fields.One2many('furniture.catalog.line', 'import_id', 'Products')
    line_count = fields.Integer(compute='_compute_counts')
    error_count = fields.Integer(compute='_compute_counts')
    imported_count = fields.Integer(compute='_compute_counts')
    image_attachment_ids = fields.Many2many('ir.attachment', 'furniture_catalog_import_image_rel',
                                            'import_id', 'attachment_id', string='Product images')
    imported_on = fields.Datetime(readonly=True)
    access_token = fields.Char(copy=False, default=lambda s: uuid.uuid4().hex)

    @api.depends('line_ids.import_state')
    def _compute_counts(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.error_count = len(rec.line_ids.filtered(lambda l: l.import_state == 'failed'))
            rec.imported_count = len(rec.line_ids.filtered(lambda l: l.import_state == 'imported'))

    # ------------------------------------------------------------------
    @api.model
    def _create_from_upload(self, filename, raw, manufacturer=None, application=None):
        """Validate the file. Returns (record|None, errors). Nothing is stored when errors exist."""
        settings = self.env['furniture.marketplace.settings'].get_settings()
        rows, errors = parse_catalog(filename, raw, max_rows=settings.catalog_max_rows or 500)
        if errors:
            return None, errors
        rec = self.sudo().create({
            'name': filename or self.env._('Catalog'),
            'filename': filename,
            'datafile': base64.b64encode(raw),
            'manufacturer_id': manufacturer.id if manufacturer else False,
            'application_id': application.id if application else False,
            'line_ids': [(0, 0, {
                'sequence': r['row_no'], 'product_name': r['product_name'], 'category': r['category'],
                'description': r['description'], 'price': r['price'], 'quantity': r['quantity'],
                'image_ref': r['image'], 'specifications': r['specifications'],
            }) for r in rows],
        })
        return rec, []

    @api.model
    def _validate_only(self, filename, raw):
        settings = self.env['furniture.marketplace.settings'].get_settings()
        return parse_catalog(filename, raw, max_rows=settings.catalog_max_rows or 500)

    # ------------------------------------------------------------------
    def _resolve_image(self, ref):
        """Return base64 image data (bytes) or False. Never raises."""
        self.ensure_one()
        if not ref:
            return False
        try:
            if ref.lower().startswith(('http://', 'https://')):
                if not _is_public_url(ref):
                    return False
                resp = requests.get(ref, timeout=(5, 10), stream=True, allow_redirects=False)
                ctype = (resp.headers.get('Content-Type') or '').lower()
                if resp.status_code != 200 or not ctype.startswith('image/') or 'svg' in ctype:
                    return False
                content = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
                if len(content) > MAX_IMAGE_BYTES:
                    return False
                return base64.b64encode(content)
            wanted = os.path.basename(ref).lower()
            attachments = self.image_attachment_ids | self.application_id.document_ids
            for att in attachments:
                if (att.name or '').lower() == wanted and att.datas:
                    return att.datas
        except Exception as exc:  # noqa: BLE001
            _logger.info('Image %s could not be fetched: %s', ref, exc)
        return False

    def action_import(self, manufacturer=None):
        """Create the products (pending approval, never published) from validated lines."""
        Product = self.env['product.template'].sudo()
        for rec in self:
            manufacturer = manufacturer or rec.manufacturer_id
            if not manufacturer:
                raise UserError(self.env._('A manufacturer is required to import the catalog.'))
            rec.manufacturer_id = manufacturer
            for line in rec.line_ids.filtered(lambda l: l.import_state != 'imported'):
                try:
                    with self.env.cr.savepoint():
                        vals = Product._marketplace_type_vals()
                        image = rec._resolve_image(line.image_ref)
                        vals.update({
                            'name': line.product_name,
                            'list_price': line.price,
                            'description_sale': line.description,
                            'categ_id': Product._marketplace_internal_category(line.category).id,
                            'public_categ_ids': [(6, 0, [Product._marketplace_public_category(line.category).id])],
                            'manufacturer_id': manufacturer.id,
                            'marketplace_specifications': line.specifications,
                            'marketplace_approval_state': 'pending',
                            'website_published': False,
                            'sale_ok': True,
                        })
                        if image:
                            vals['image_1920'] = image
                        product = Product.create(vals)
                        if line.quantity > 0:
                            product._marketplace_set_quantity(line.quantity)
                        line.write({'product_id': product.id, 'import_state': 'imported',
                                    'warning': (self.env._('Image could not be loaded.')
                                                if line.image_ref and not image else False)})
                except Exception as exc:  # noqa: BLE001 - keep importing the remaining lines
                    _logger.exception('Catalog line %s failed', line.id)
                    line.write({'import_state': 'failed', 'error_message': str(exc)[:500]})
            rec.write({'state': 'imported', 'imported_on': fields.Datetime.now()})
        return True


class FurnitureCatalogLine(models.Model):
    _name = 'furniture.catalog.line'
    _description = 'Catalog Line'
    _order = 'sequence, id'

    import_id = fields.Many2one('furniture.catalog.import', required=True, ondelete='cascade', index=True)
    manufacturer_id = fields.Many2one(related='import_id.manufacturer_id', store=True, index=True)
    sequence = fields.Integer('Row')
    product_name = fields.Char(required=True)
    category = fields.Char(required=True)
    description = fields.Text()
    price = fields.Float()
    quantity = fields.Float()
    image_ref = fields.Char('Image')
    specifications = fields.Text()
    import_state = fields.Selection([('pending', 'Pending'), ('imported', 'Imported'), ('failed', 'Failed')],
                                    default='pending')
    product_id = fields.Many2one('product.template', ondelete='set null')
    error_message = fields.Char()
    warning = fields.Char()
