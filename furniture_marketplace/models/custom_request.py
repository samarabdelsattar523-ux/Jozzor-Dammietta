# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import check_marketplace_manager

STATES = [
    ('draft', 'Draft'), ('submitted', 'Submitted'), ('under_review', 'Under Review'),
    ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('quotation', 'Quotation Sent'),
    ('confirmed', 'Confirmed'), ('in_production', 'In Production'),
    ('completed', 'Completed'), ('cancelled', 'Cancelled'),
]
NOTIFY_STATES = ('under_review', 'accepted', 'rejected', 'quotation', 'confirmed',
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
    partner_id = fields.Many2one('res.partner', 'Customer', required=True, index=True,
                                 default=lambda s: s.env.user.partner_id)
    customer_email = fields.Char(related='partner_id.email')
    customer_phone = fields.Char(related='partner_id.phone')
    request_date = fields.Date(default=fields.Date.context_today, readonly=True)
    state = fields.Selection(STATES, default='draft', required=True, tracking=True, copy=False, index=True)
    rejection_reason = fields.Text(copy=False)
    currency_id = fields.Many2one('res.currency', default=lambda s: s.env.company.currency_id)
    agreed_price = fields.Monetary('Agreed Price', currency_field='currency_id', tracking=True)
    commercial_terms = fields.Text('Agreed Commercial Terms')
    sale_order_id = fields.Many2one('sale.order', 'Quotation / Order', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furniture.custom.request') or self.env._('New')
        return super().create(vals_list)

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

    def action_create_quotation(self):
        check_marketplace_manager(self.env)
        product = self.env.ref('furniture_marketplace.product_custom_manufacturing').product_variant_id
        for rec in self:
            if rec.state != 'accepted':
                raise UserError(self.env._('The request must be accepted before a quotation is created.'))
            if rec.agreed_price <= 0:
                raise UserError(self.env._('Enter the agreed price before creating the quotation.'))
            order = self.env['sale.order'].sudo().create({  # manager rights checked above
                'partner_id': rec.partner_id.id,
                'origin': rec.name,
                'note': rec.commercial_terms or False,
                'order_line': [(0, 0, {
                    'product_id': product.id,
                    'name': '%s\n%s' % (rec.title, rec.description),
                    'product_uom_qty': 1,
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
