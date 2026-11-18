# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FurnitureWorkshopSize(models.Model):
    _name = 'furniture.workshop.size'
    _description = 'Workshop Size'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class FurnitureManufacturerType(models.Model):
    _name = 'furniture.manufacturer.type'
    _description = 'Manufacturer Category / Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class FurnitureMarketplaceSettings(models.Model):
    """Single-record settings model (robust across Odoo versions, no res.config.settings view hacks)."""
    _name = 'furniture.marketplace.settings'
    _description = 'Marketplace Settings'

    name = fields.Char(default='Marketplace Settings', readonly=True)
    # Marketplace
    products_per_page = fields.Integer(default=12, string='Products per page')
    # Manufacturer approval
    notify_email = fields.Char(string='Notify e-mail for new applications')
    auto_import_catalog = fields.Boolean(
        default=True, string='Import catalog automatically on approval')
    # Product approval
    auto_publish_on_approval = fields.Boolean(
        default=False, string='Publish product automatically once approved')
    catalog_max_rows = fields.Integer(default=500, string='Max products per catalog file')
    # Portal permissions
    portal_allow_profile_edit = fields.Boolean(default=True, string='Manufacturers can edit their profile')
    portal_allow_product_create = fields.Boolean(default=True, string='Manufacturers can create/edit products')
    portal_allow_catalog_upload = fields.Boolean(default=True, string='Manufacturers can upload catalogs')
    portal_allow_stock_update = fields.Boolean(default=True, string='Manufacturers can update stock quantity')
    portal_allow_request_review = fields.Boolean(
        default=True, string='Manufacturers can accept/reject/progress custom requests')
    customer_allow_request_cancel = fields.Boolean(
        default=True, string='Customers can cancel their own custom requests')

    @api.model
    def get_settings(self):
        rec = self.sudo().search([], limit=1)
        return rec or self.sudo().create({})
