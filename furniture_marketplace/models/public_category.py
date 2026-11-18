# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    marketplace_product_count = fields.Integer(
        'Published products', compute='_compute_marketplace_product_count',
        help='Published and approved marketplace products in this category and its sub-categories.')

    def _compute_marketplace_product_count(self):
        Product = self.env['product.template'].sudo()
        base = Product._marketplace_visible_domain()
        for cat in self:
            cat.marketplace_product_count = Product.search_count(
                base + [('public_categ_ids', 'child_of', cat.id)])
