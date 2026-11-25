# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import check_marketplace_manager

ALLOCATION_STATES = [
    ('new', 'New'), ('accepted', 'Accepted'), ('preparing', 'Preparing'),
    ('ready', 'Ready for Dispatch'), ('dispatched', 'Dispatched'), ('delivered', 'Delivered'),
    ('exception', 'Exception'), ('cancelled', 'Cancelled'),
]
# status changes a manufacturer may make on its own allocation (spec 8.4)
MANUFACTURER_TRANSITIONS = {
    'accept': ('new', 'accepted'),
    'prepare': ('accepted', 'preparing'),
    'ready': ('preparing', 'ready'),
    'dispatch': ('ready', 'dispatched'),
}


class FurnitureOrderAllocation(models.Model):
    """The part of one customer order that one manufacturer must fulfil.

    The customer keeps a single sales order and a single payment; each
    manufacturer only sees and processes its own allocation.
    """
    _name = 'furniture.order.allocation'
    _description = 'Manufacturer Fulfilment Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, readonly=True)
    order_id = fields.Many2one('sale.order', 'Customer Order', required=True, readonly=True,
                               ondelete='cascade', index=True)
    manufacturer_id = fields.Many2one('furniture.manufacturer', 'Manufacturer / Workshop', required=True,
                                      readonly=True, index=True)
    line_ids = fields.One2many('sale.order.line', 'allocation_id', 'Order Lines', readonly=True)
    partner_id = fields.Many2one(related='order_id.partner_id', string='Customer')
    partner_shipping_id = fields.Many2one(related='order_id.partner_shipping_id', string='Delivery Address')
    date_order = fields.Datetime(related='order_id.date_order', string='Order Date')
    currency_id = fields.Many2one(related='order_id.currency_id')
    amount_untaxed = fields.Monetary(compute='_compute_amount', currency_field='currency_id', string='Amount')
    state = fields.Selection(ALLOCATION_STATES, default='new', required=True, tracking=True, index=True)
    exception_note = fields.Text('Exception Details', tracking=True)
    picking_ids = fields.Many2many('stock.picking', compute='_compute_picking_ids', string='Deliveries')

    _order_manufacturer_unique = models.Constraint(
        'UNIQUE(order_id, manufacturer_id)', 'One allocation per order and manufacturer.')

    @api.depends('line_ids.price_subtotal')
    def _compute_amount(self):
        for rec in self:
            rec.amount_untaxed = sum(rec.line_ids.mapped('price_subtotal'))

    @api.depends('line_ids')
    def _compute_picking_ids(self):
        for rec in self:
            moves = rec.line_ids.sudo().mapped('move_ids') if 'move_ids' in rec.line_ids._fields else []
            rec.picking_ids = moves.mapped('picking_id') if moves else False

    def state_label(self):
        self.ensure_one()
        return dict(self._fields['state']._description_selection(self.env)).get(self.state, self.state)

    # ------------------------------------------------------------------
    @api.model
    def _create_for_orders(self, orders):
        """Group the lines of confirmed orders by manufacturer (idempotent)."""
        created = self.browse()
        for order in orders.sudo():
            lines_by_maker = {}
            for line in order.order_line.filtered(lambda l: l.manufacturer_id and not l.display_type):
                lines_by_maker.setdefault(line.manufacturer_id, self.env['sale.order.line'])
                lines_by_maker[line.manufacturer_id] |= line
            for maker, lines in lines_by_maker.items():
                alloc = self.sudo().search([('order_id', '=', order.id), ('manufacturer_id', '=', maker.id)], limit=1)
                if not alloc:
                    alloc = self.sudo().create({
                        'name': '%s / %s' % (order.name, maker.name),
                        'order_id': order.id, 'manufacturer_id': maker.id,
                    })
                    created |= alloc
                lines.write({'allocation_id': alloc.id})
        for alloc in created:
            partner = alloc.manufacturer_id.partner_id
            if partner:
                alloc.message_post(
                    body=self.env._('New order lines were assigned to you for fulfilment: %s', alloc.name),
                    partner_ids=partner.ids, subtype_xmlid='mail.mt_comment')
        return created

    def _manufacturer_transition(self, action):
        """Used by the manufacturer portal: only the forward steps in MANUFACTURER_TRANSITIONS."""
        spec = MANUFACTURER_TRANSITIONS.get(action)
        for rec in self:
            if not spec or rec.state != spec[0]:
                raise UserError(self.env._('This status change is not allowed.'))
            rec.state = spec[1]
            rec.order_id.message_post(body=self.env._('%(maker)s: fulfilment status is now %(state)s.',
                                                      maker=rec.manufacturer_id.name, state=rec.state_label()))

    def _report_exception(self, note):
        """Manufacturer cannot fulfil: the platform decides (cancel, substitute, refund)."""
        for rec in self.filtered(lambda r: r.state not in ('delivered', 'cancelled')):
            rec.write({'state': 'exception', 'exception_note': note})
            rec.activity_schedule('mail.mail_activity_data_todo',
                                  summary=self.env._('Fulfilment exception: %s', rec.name), note=note,
                                  user_id=rec.order_id.user_id.id or self.env.ref('base.user_admin').id)

    # --- platform (manager) actions ---
    def action_mark_delivered(self):
        check_marketplace_manager(self.env)
        self.write({'state': 'delivered'})

    def action_cancel(self):
        check_marketplace_manager(self.env)
        self.write({'state': 'cancelled'})

    def action_reset_new(self):
        check_marketplace_manager(self.env)
        self.write({'state': 'new', 'exception_note': False})
