from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    manufacturer_id = fields.Many2one(
        'furniture.manufacturer',
        string='Manufacturer',
        related='product_id.product_tmpl_id.manufacturer_id',
        store=True,
        index=True,
        readonly=True,
    )

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    marketplace_manufacturer_ids = fields.Many2many(
        'furniture.manufacturer',
        string='Manufacturers',
        compute='_compute_marketplace_manufacturers',
    )

    def _compute_marketplace_manufacturers(self):
        for order in self:
            order.marketplace_manufacturer_ids = order.order_line.mapped('manufacturer_id')
