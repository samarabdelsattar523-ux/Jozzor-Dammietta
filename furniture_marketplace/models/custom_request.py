# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import check_marketplace_manager

STATES = [
    ('draft', 'Draft'), ('submitted', 'Submitted'), ('under_review', 'Under Review'),
    ('quoted', 'Quotation Submitted'), ('accepted', 'Accepted'), ('rejected', 'Rejected'),
    ('quotation', 'Converted to Order'),
    ('confirmed', 'Confirmed'), ('in_production', 'In Production'),
    ('completed', 'Completed'), ('cancelled', 'Cancelled'),
]
NOTIFY_STATES = ('under_review', 'quoted', 'accepted', 'rejected', 'quotation', 'confirmed',
                 'in_production', 'completed', 'cancelled')


class FurnitureCustomRequest(models.Model):
    _name = 'furniture.custom.request'
    _description = 'Custom Furniture Manufacturing Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'id desc'

    name = fields.Char('Reference', readonly=True, copy=False, default=lambda s: s.env._('New'))
    title = fields.Char('Request Title', required=True, tracking=True)
    description = fields.Text('Furniture Description', required=True)
    reference_image = fields.Binary('Reference Image', attachment=True, required=True)
    reference_image_name = fields.Char()
    manufacturer_id = fields.Many2one('furniture.manufacturer', 'Preferred Manufacturer', required=True,
                                      domain=[('approved', '=', True)], tracking=True, index=True)
    notes = fields.Text('Additional Notes')
    public_categ_id = fields.Many2one('product.public.category', 'Furniture Category', tracking=True)
    quantity = fields.Integer('Quantity', default=1, tracking=True)
    length_cm = fields.Float('Length (cm)')
    width_cm = fields.Float('Width (cm)')
    height_cm = fields.Float('Height (cm)')
    delivery_address = fields.Text('Delivery Location')
    partner_id = fields.Many2one('res.partner', 'Customer', required=True, index=True,
                                 default=lambda s: s.env.user.partner_id)
    customer_email = fields.Char(related='partner_id.email')
    customer_phone = fields.Char(related='partner_id.phone')
    request_date = fields.Date(default=fields.Date.context_today, readonly=True)
    state = fields.Selection(STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    rejection_reason = fields.Text(copy=False)
    currency_id = fields.Many2one('res.currency', default=lambda s: s.env.company.currency_id)
    agreed_price = fields.Monetary('Unit Price', currency_field='currency_id', tracking=True)
    lead_time_days = fields.Integer('Lead Time (days)', tracking=True)
    commercial_terms = fields.Text('Commercial Terms')
    quoted_on = fields.Datetime(readonly=True, copy=False)
    amount_total = fields.Monetary('Quoted Total', currency_field='currency_id', compute='_compute_amount_total')
    sale_order_id = fields.Many2one('sale.order', 'Quotation / Order', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furniture.custom.request') or self.env._('New')
        return super().create(vals_list)

    @api.depends('agreed_price', 'quantity')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = rec.agreed_price * max(rec.quantity, 1)

    def dimensions_label(self):
        self.ensure_one()
        dims = [self.length_cm, self.width_cm, self.height_cm]
        return ' x '.join('%g' % d for d in dims) + ' cm' if any(dims) else ''

    def _compute_access_url(self):
        super()._compute_access_url()
        for rec in self:
            rec.access_url = '/my/furniture-requests/%s' % rec.id

    def state_label(self):
        self.ensure_one()
        return dict(self._fields['state']._description_selection(self.env)).get(self.state, self.state)

    # ------------------------------------------------------------------
    def _send_template(self, xmlid):
        template = self.env.ref('furniture_marketplace.%s' % xmlid, raise_if_not_found=False)
        for rec in self:
            if template:
                template.sudo().send_mail(rec.id, force_send=True)

    def _set_state(self, new_state):
        for rec in self:
            rec.write({'state': new_state})
            if new_state in NOTIFY_STATES:
                rec._send_template('mail_request_state_changed')

    # --- workflow buttons (also reused by the manufacturer portal controller) ---
    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            rec.write({'state': 'submitted'})
            rec._send_template('mail_request_submitted_customer')
            rec._send_template('mail_request_submitted_manufacturer')

    def action_start_review(self):
        self.filtered(lambda r: r.state == 'submitted')._set_state('under_review')

    def action_accept(self):
        self.filtered(lambda r: r.state in ('submitted', 'under_review'))._set_state('accepted')

    def action_reject(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Reject Request'),
            'res_model': 'furniture.reject.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }

    def _do_reject(self, reason):
        for rec in self.filtered(lambda r: r.state in ('submitted', 'under_review')):
            rec.rejection_reason = reason
            rec._set_state('rejected')

    # --- quotation round: manufacturer (or platform) quotes, customer decides ---
    def action_send_quote(self, price=None, lead_time=None, terms=None):
        """Submit the price to the customer. Values default to what is already on the request."""
        for rec in self:
            if rec.state not in ('submitted', 'under_review'):
                raise UserError(self.env._('A quotation can only be sent for a request under review.'))
            vals = {'quoted_on': fields.Datetime.now()}
            if price is not None:
                vals['agreed_price'] = price
            if lead_time is not None:
                vals['lead_time_days'] = lead_time
            if terms is not None:
                vals['commercial_terms'] = terms
            rec.write(vals)
            if rec.agreed_price <= 0:
                raise UserError(self.env._('Enter a unit price greater than zero.'))
            rec._set_state('quoted')

    def action_customer_accept(self):
        """Customer accepts the quotation: a sales quotation is created for payment / confirmation.
        Payment and production still follow the normal order flow (spec 6.2)."""
        for rec in self.filtered(lambda r: r.state == 'quoted'):
            rec._set_state('accepted')
            rec.message_post(body=self.env._('The customer accepted the quotation.'))
            rec.sudo()._create_sale_order()

    def action_customer_reject(self, reason=''):
        for rec in self.filtered(lambda r: r.state == 'quoted'):
            rec.rejection_reason = self.env._('Declined by the customer: %s', reason or '-')
            rec._set_state('rejected')

    def action_create_quotation(self):
        check_marketplace_manager(self.env)
        for rec in self:
            if rec.state != 'accepted':
                raise UserError(self.env._('The request must be accepted before a quotation is created.'))
            if rec.agreed_price <= 0:
                raise UserError(self.env._('Enter the agreed price before creating the quotation.'))
            rec.sudo()._create_sale_order()  # manager rights checked above

    def _create_sale_order(self):
        product = self.env.ref('furniture_marketplace.product_custom_manufacturing').product_variant_id
        for rec in self.filtered(lambda r: not r.sale_order_id):
            lines = [rec.title, rec.description]
            if rec.dimensions_label():
                lines.append(self.env._('Dimensions: %s', rec.dimensions_label()))
            if rec.lead_time_days:
                lines.append(self.env._('Lead time: %s days', rec.lead_time_days))
            order = self.env['sale.order'].create({
                'partner_id': rec.partner_id.id,
                'origin': rec.name,
                'note': rec.commercial_terms or False,
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': '\n'.join(lines),
                    'product_uom_qty': max(rec.quantity, 1),
                    'price_unit': rec.agreed_price,
                })],
            })
            rec.write({'sale_order_id': order.id})
            rec._set_state('quotation')

    def action_confirm_request(self):
        self.filtered(lambda r: r.state == 'quotation')._set_state('confirmed')

    def action_start_production(self):
        self.filtered(lambda r: r.state == 'confirmed')._set_state('in_production')

    def action_complete(self):
        self.filtered(lambda r: r.state == 'in_production')._set_state('completed')

    def action_cancel(self):
        self.filtered(lambda r: r.state not in ('completed', 'cancelled'))._set_state('cancelled')

    def action_view_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'view_mode': 'form',
                'res_id': self.sale_order_id.id}
