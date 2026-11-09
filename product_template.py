# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    maker_id = fields.Many2one('jozoor.maker', string='Damietta Maker / Workshop')
    is_jozoor_featured = fields.Boolean(string='Featured on Jozoor', default=True)
    jozoor_card_color = fields.Char(string='Card Background Class', default='bg-[#e8dfd3]')
    jozoor_availability = fields.Selection([
        ('in_stock', 'In Stock'),
        ('made_to_order', 'Made to order'),
    ], string='Jozoor Availability', default='in_stock')
    jozoor_image_url = fields.Char(string='External Image URL')
