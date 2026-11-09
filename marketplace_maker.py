# -*- coding: utf-8 -*-
from odoo import models, fields, api

class JozoorMaker(models.Model):
    _name = 'jozoor.maker'
    _description = 'Furniture Workshop / Maker'
    _order = 'name asc'

    name = fields.Char(string='Workshop Name', required=True)
    location = fields.Char(string='Location', default='Damietta, Egypt')
    initials = fields.Char(string='Initials', compute='_compute_initials', store=True)
    image_url = fields.Char(string='Image URL')
    image_1920 = fields.Image(string='Workshop Photo')
    rating = fields.Float(string='Rating', default=4.9)
    bio = fields.Text(string='About Workshop')
    partner_id = fields.Many2one('res.partner', string='Linked Partner')
    product_ids = fields.One2many('product.template', 'maker_id', string='Products')
    product_count = fields.Integer(string='Product Count', compute='_compute_product_count')

    @api.depends('name')
    def _compute_initials(self):
        for rec in self:
            if rec.name:
                parts = rec.name.split()
                rec.initials = ''.join([p[0].upper() for p in parts[:2]])
            else:
                rec.initials = 'JM'

    @api.depends('product_ids')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)
