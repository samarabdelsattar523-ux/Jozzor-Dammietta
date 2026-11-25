# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .utils import check_marketplace_manager

_logger = logging.getLogger(__name__)


class FurnitureManufacturerApplication(models.Model):
    _name = 'furniture.manufacturer.application'
    _description = 'Manufacturer Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Reference', readonly=True, copy=False, default=lambda s: s.env._('New'))
    manufacturer_name = fields.Char('Manufacturer / Workshop Name', required=True, tracking=True)
    representative = fields.Char('Owner / Authorized Representative', required=True)
    email = fields.Char('Email', required=True, tracking=True)
    phone = fields.Char('Mobile Number', required=True)
    address = fields.Text('Detailed Address', required=False)
    country_id = fields.Many2one('res.country', 'Country', required=True)
    city = fields.Char(required=True)
    workshop_size_id = fields.Many2one('furniture.workshop.size', 'Workshop Size', required=True)
    description = fields.Text('Workshop Description')
    registration_date = fields.Date(default=fields.Date.context_today, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Pending Approval'),
        ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='draft', required=True, tracking=True, copy=False)
    rejection_reason = fields.Text(copy=False, tracking=True)
    internal_notes = fields.Html('Internal Notes')
    catalog_import_id = fields.Many2one('furniture.catalog.import', 'Product Catalog', copy=False)
    catalog_line_ids = fields.One2many(related='catalog_import_id.line_ids', string='Catalog Products')
    catalog_file = fields.Binary(related='catalog_import_id.datafile', string='Catalog File')
    catalog_filename = fields.Char(related='catalog_import_id.filename')
    document_ids = fields.Many2many('ir.attachment', 'furniture_application_attachment_rel',
                                    'application_id', 'attachment_id', string='Additional Documents')
    manufacturer_id = fields.Many2one('furniture.manufacturer', 'Manufacturer', readonly=True, copy=False)
    submitted_on = fields.Datetime(readonly=True, copy=False)
    reviewed_by = fields.Many2one('res.users', readonly=True, copy=False)
    reviewed_on = fields.Datetime(readonly=True, copy=False)
    access_token = fields.Char(copy=False, default=lambda s: uuid.uuid4().hex)
    from_website = fields.Boolean(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('furniture.manufacturer.application') or self.env._('New')
        return super().create(vals_list)

    def state_label(self):
        self.ensure_one()
        return dict(self._fields['state']._description_selection(self.env)).get(self.state, self.state)

    # ------------------------------------------------------------------
    def _send_template(self, xmlid):
        template = self.env.ref('furniture_marketplace.%s' % xmlid, raise_if_not_found=False)
        for rec in self:
            if template:
                template.sudo().send_mail(rec.id, force_send=True)

    def _notify_internal(self):
        email = self.env['furniture.marketplace.settings'].get_settings().notify_email
        if not email:
            return
        for rec in self:
            self.env['mail.mail'].sudo().create({
                'subject': self.env._('New manufacturer application %s', rec.name),
                'body_html': self.env._('<p>A new application from <b>%(name)s</b> (%(ref)s) is waiting for approval.</p>',
                               name=rec.manufacturer_name, ref=rec.name),
                'email_to': email,
            }).send()

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.catalog_import_id:
                raise UserError(self.env._('The product catalog is required before submitting.'))
            rec.write({'state': 'submitted', 'submitted_on': fields.Datetime.now()})
            rec._send_template('mail_application_received')
            rec._notify_internal()

    def action_reset_draft(self):
        check_marketplace_manager(self.env)
        self.filtered(lambda r: r.state == 'rejected').write({'state': 'draft', 'rejection_reason': False})

    # ------------------------------------------------------------------
    def _create_or_link_manufacturer(self):
        self.ensure_one()
        Partner = self.env['res.partner'].sudo()
        Manufacturer = self.env['furniture.manufacturer'].sudo().with_context(active_test=False)
        partner = Partner.search([('email', '=ilike', self.email)], limit=1)
        values = {
            'name': self.manufacturer_name, 'email': self.email, 'phone': self.phone,
            'street': self.address or False, 'city': self.city, 'country_id': self.country_id.id,
            'is_company': True,
        }
        if partner:  # link: only fill what is empty, never overwrite or retype an existing contact
            fill = {k: v for k, v in values.items()
                    if k != 'is_company' and not partner[k]}
            if fill:
                partner.write(fill)
        else:
            partner = Partner.create(values)
        manufacturer = Manufacturer.search([('partner_id', '=', partner.id)], limit=1)
        mvals = {
            'name': self.manufacturer_name, 'partner_id': partner.id, 'representative': self.representative,
            'address': self.address or False, 'city': self.city, 'country_id': self.country_id.id,
            'workshop_size_id': self.workshop_size_id.id, 'description': self.description,
            'application_id': self.id, 'approved': True, 'active': True,
        }
        if manufacturer:
            manufacturer.write(mvals)
        else:
            manufacturer = Manufacturer.create(mvals)
        return manufacturer

    def action_approve(self):
        check_marketplace_manager(self.env)
        settings = self.env['furniture.marketplace.settings'].get_settings()
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(self.env._('Only applications pending approval can be approved.'))
            manufacturer = rec._create_or_link_manufacturer()
            manufacturer._provision_portal_user()
            rec.write({'state': 'approved', 'manufacturer_id': manufacturer.id,
                       'reviewed_by': self.env.user.id, 'reviewed_on': fields.Datetime.now(),
                       'rejection_reason': False})
            if settings.auto_import_catalog and rec.catalog_import_id and rec.catalog_import_id.state == 'draft':
                rec.catalog_import_id.action_import(manufacturer)
                rec.message_post(body=self.env._('Catalog imported: %(ok)s product(s) created, %(ko)s failed. '
                                        'Products stay unpublished until approved.',
                                        ok=rec.catalog_import_id.imported_count, ko=rec.catalog_import_id.error_count))
            rec._send_template('mail_application_approved')

    def action_reject(self):
        check_marketplace_manager(self.env)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Reject Application'),
            'res_model': 'furniture.reject.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }

    def _do_reject(self, reason):
        check_marketplace_manager(self.env)
        for rec in self:
            if rec.state not in ('submitted', 'draft'):
                raise UserError(self.env._('This application cannot be rejected in its current state.'))
            rec.write({'state': 'rejected', 'rejection_reason': reason,
                       'reviewed_by': self.env.user.id, 'reviewed_on': fields.Datetime.now()})
            rec._send_template('mail_application_rejected')

    @api.model
    def _cron_cleanup_drafts(self):
        """Remove abandoned website drafts (applicant never pressed 'Submit Application')."""
        limit = fields.Datetime.now() - timedelta(days=7)
        self.sudo().search([('state', '=', 'draft'), ('from_website', '=', True),
                            ('create_date', '<', limit)]).unlink()
