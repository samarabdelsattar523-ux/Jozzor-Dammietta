# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import GROUP_MANUFACTURER, check_marketplace_manager

_logger = logging.getLogger(__name__)


class FurnitureManufacturer(models.Model):
    _name = 'furniture.manufacturer'
    _description = 'Furniture Manufacturer / Workshop'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('Manufacturer / Workshop', required=True, tracking=True)
    active = fields.Boolean(default=True)
    approved = fields.Boolean('Approved / Active in Marketplace', default=True, tracking=True)
    partner_id = fields.Many2one('res.partner', 'Contact', required=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', 'Portal User', ondelete='set null', copy=False)
    type_id = fields.Many2one('furniture.manufacturer.type', 'Category / Type')
    representative = fields.Char('Owner / Representative')
    email = fields.Char(related='partner_id.email', readonly=False, store=True)
    phone = fields.Char(related='partner_id.phone', readonly=False)
    address = fields.Text('Detailed Address')
    city = fields.Char()
    country_id = fields.Many2one('res.country')
    workshop_size_id = fields.Many2one('furniture.workshop.size', 'Workshop Size')
    description = fields.Text('Workshop Description')
    application_id = fields.Many2one('furniture.manufacturer.application', 'Application', copy=False)
    product_ids = fields.One2many('product.template', 'manufacturer_id', 'Products')
    product_count = fields.Integer(compute='_compute_counts')
    request_count = fields.Integer(compute='_compute_counts')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.constrains('email')
    def _check_unique_email(self):
        for rec in self:
            if rec.email and self.with_context(active_test=False).search_count(
                    [('email', '=ilike', rec.email), ('id', '!=', rec.id)]):
                raise UserError(self.env._('Another manufacturer already uses the e-mail %s.', rec.email))

    @api.depends('product_ids')
    def _compute_counts(self):
        Request = self.env['furniture.custom.request'].sudo()
        for rec in self:
            rec.product_count = len(rec.product_ids)
            rec.request_count = Request.search_count([('manufacturer_id', '=', rec.id)])

    # ------------------------------------------------------------------
    # Portal user provisioning (shared by application approval + manual)
    # ------------------------------------------------------------------
    def _provision_portal_user(self):
        self.ensure_one()
        if not self.email:
            raise UserError(self.env._('The manufacturer needs an e-mail address to create a portal user.'))
        group = self.env.ref(GROUP_MANUFACTURER)
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        user = Users.search([('login', '=ilike', self.email)], limit=1)
        if user:
            if not user.share:
                raise UserError(self.env._('%s belongs to an internal user; a portal account cannot be created '
                                  'with the same login.', self.email))
            if user.partner_id != self.partner_id:
                raise UserError(self.env._('A user with login %s already exists for a different contact.',
                                  self.email))
            user.write({'group_ids': [(4, group.id)], 'active': True})
        else:
            # NB: do not pass name/email: they are related to the partner and would rename it.
            user = Users.with_context(no_reset_password=True).create({
                'login': self.email,
                'partner_id': self.partner_id.id,
                'group_ids': [(6, 0, [group.id])],
            })
        self.sudo().write({'user_id': user.id})
        try:
            user.with_context(create_user=True).action_reset_password()
        except Exception as exc:  # mail server problems must not block the approval
            _logger.warning('Invitation e-mail for %s could not be sent: %s', self.email, exc)
            self.message_post(body=self.env._('The invitation e-mail could not be sent (%s). '
                                     'Use "Send invitation" once the outgoing mail server works.', exc))
        return user

    def action_create_portal_user(self):
        check_marketplace_manager(self.env)
        for rec in self:
            rec._provision_portal_user()

    def action_suspend(self):
        check_marketplace_manager(self.env)
        for rec in self:
            rec.approved = False
            if rec.user_id:
                rec.user_id.sudo().active = False
            rec.product_ids.filtered('website_published').sudo().write({'website_published': False})

    def action_activate(self):
        check_marketplace_manager(self.env)
        for rec in self:
            rec.approved = True
            if rec.user_id:
                rec.user_id.sudo().active = True

    def action_view_products(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Products'),
            'res_model': 'product.template', 'view_mode': 'list,form',
            'domain': [('manufacturer_id', '=', self.id)],
            'context': {'default_manufacturer_id': self.id,
                        'default_marketplace_approval_state': 'pending'},
        }

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Custom Requests'),
            'res_model': 'furniture.custom.request', 'view_mode': 'list,form',
            'domain': [('manufacturer_id', '=', self.id)],
        }
