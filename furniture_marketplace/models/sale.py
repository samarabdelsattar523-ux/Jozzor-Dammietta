# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    manufacturer_id = fields.Many2one(
        'furniture.manufacturer', string='Manufacturer / Workshop',
        related='product_id.product_tmpl_id.manufacturer_id', store=True, readonly=True, index=True)
    allocation_id = fields.Many2one('furniture.order.allocation', 'Fulfilment Allocation',
                                    readonly=True, copy=False, index=True, ondelete='set null')

    def _compute_name_short(self):
        # one cart / one order: every line shows which workshop provides it
        if hasattr(super(), '_compute_name_short'):
            super()._compute_name_short()
        if 'name_short' not in self._fields:
            return
        for line in self:
            maker = line.product_id.product_tmpl_id.sudo().manufacturer_id
            if maker and line.name_short:
                line.name_short = '%s — %s' % (line.name_short, maker.name)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    manufacturer_ids = fields.Many2many(
        'furniture.manufacturer', string='Manufacturers', compute='_compute_manufacturer_ids')
    allocation_ids = fields.One2many('furniture.order.allocation', 'order_id', 'Manufacturer Fulfilment')

    @api.depends('order_line.manufacturer_id')
    def _compute_manufacturer_ids(self):
        for order in self:
            order.manufacturer_ids = order.order_line.sudo().mapped('manufacturer_id')

    def action_confirm(self):
        res = super().action_confirm()
        self.env['furniture.order.allocation']._create_for_orders(self)
        requests = self.env['furniture.custom.request'].sudo().search(
            [('sale_order_id', 'in', self.ids), ('state', '=', 'quotation')])
        for req in requests:
            req._set_state('confirmed')
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        self.sudo().allocation_ids.filtered(lambda a: a.state != 'delivered').write({'state': 'cancelled'})
        return res
