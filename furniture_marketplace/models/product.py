# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .utils import check_marketplace_manager, is_manufacturer_portal_user, split_category_path

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    manufacturer_id = fields.Many2one(
        'furniture.manufacturer', 'Manufacturer / Workshop', index=True, tracking=True,
        ondelete='restrict', help='Workshop responsible for this product.')
    marketplace_approval_state = fields.Selection([
        ('not_required', 'Not a marketplace product'), ('pending', 'Pending Approval'),
        ('approved', 'Approved'), ('rejected', 'Rejected')],
        string='Marketplace Approval', default='not_required', index=True, copy=False, tracking=True)
    marketplace_rejection_reason = fields.Text(copy=False)
    marketplace_specifications = fields.Text('Specifications', translate=True,
                                             help='One per line or separated by ";" e.g. Material: Oak')
    marketplace_manufacturer_name = fields.Char(compute='_compute_marketplace_manufacturer_name')
    marketplace_available_qty = fields.Float(compute='_compute_marketplace_stock')
    marketplace_stock_status = fields.Selection(
        [('in_stock', 'In Stock'), ('low_stock', 'Low Stock'),
         ('out_of_stock', 'Out of Stock'), ('unlimited', 'Available')],
        compute='_compute_marketplace_stock')

    # ------------------------------------------------------------------
    # Compute (sudo: public visitors cannot read manufacturers / stock quants)
    # ------------------------------------------------------------------
    @api.depends('manufacturer_id')
    def _compute_marketplace_manufacturer_name(self):
        for rec in self:
            rec.marketplace_manufacturer_name = rec.sudo().manufacturer_id.name or False

    @api.depends_context('uid', 'warehouse_id')
    def _compute_marketplace_stock(self):
        for rec in self:
            s = rec.sudo()
            storable = s.is_storable if 'is_storable' in s._fields else s.type == 'product'
            if not storable:
                rec.marketplace_available_qty = 0.0
                rec.marketplace_stock_status = 'unlimited'
                continue
            qty = s.free_qty
            rec.marketplace_available_qty = qty
            rec.marketplace_stock_status = ('out_of_stock' if qty <= 0
                                            else 'low_stock' if qty <= 5 else 'in_stock')

    def get_marketplace_specs(self):
        """[(label, value)] for website display."""
        self.ensure_one()
        out = []
        for chunk in (self.marketplace_specifications or '').replace(';', '\n').splitlines():
            chunk = chunk.strip()
            if not chunk:
                continue
            key, sep, val = chunk.partition(':')
            out.append((key.strip(), val.strip()) if sep else (self.env._('Specification'), chunk))
        return out

    @api.model
    def _marketplace_visible_domain(self):
        return [('sale_ok', '=', True), ('website_published', '=', True),
                ('manufacturer_id', '!=', False), ('marketplace_approval_state', '=', 'approved'),
                ('manufacturer_id.approved', '=', True)]

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('manufacturer_id', 'marketplace_approval_state', 'is_published')
    def _check_marketplace_consistency(self):
        for rec in self:
            if rec.marketplace_approval_state != 'not_required' and not rec.manufacturer_id:
                raise ValidationError(self.env._('Every marketplace product must be linked to a manufacturer / workshop.'))
            if rec.manufacturer_id and rec.is_published and rec.marketplace_approval_state != 'approved':
                raise ValidationError(self.env._(
                    '"%s" cannot be published before the platform approves it. '
                    'Approve it from the Marketplace tab first.', rec.name))

    # ------------------------------------------------------------------
    # Server-side isolation of manufacturer portal users
    # ------------------------------------------------------------------
    def _own_manufacturer(self):
        return self.env['furniture.manufacturer'].sudo().search(
            [('user_id', '=', self.env.user.id), ('approved', '=', True)], limit=1)

    @staticmethod
    def _marketplace_normalize_publish(vals):
        """website_published is only a related alias of the stored is_published
        (website.published.mixin); work on is_published so both keys behave the same."""
        vals = dict(vals)
        if 'website_published' in vals:
            published = vals.pop('website_published')
            vals.setdefault('is_published', published)
        return vals

    def _marketplace_resolve(self, vals, is_mgr):
        """Extra values that keep manufacturer / approval / publication consistent
        for one record (or a new record when self is empty) after ``vals``.

        * a product gets a manufacturer -> it becomes a marketplace product
          (approved when a platform manager publishes it, otherwise pending);
        * a product left published by a change that did not ask for it (e.g. a
          pending product edited, sent back to pending/rejected) is unpublished
          instead of blocking the save;
        * only an explicit publish of an unapproved product still raises the
          constraint error: approval goes through "Approve Product".
        """
        extra = {}
        maker = vals['manufacturer_id'] if 'manufacturer_id' in vals else self.manufacturer_id.id
        state = vals.get('marketplace_approval_state', self.marketplace_approval_state or 'not_required')
        published = vals['is_published'] if 'is_published' in vals else self.is_published
        if not maker:
            if 'manufacturer_id' in vals and state != 'not_required' and 'marketplace_approval_state' not in vals:
                extra['marketplace_approval_state'] = 'not_required'
            return extra
        if state == 'not_required':
            state = 'approved' if (published and is_mgr) else 'pending'
            extra['marketplace_approval_state'] = state
        if published and state != 'approved' and not vals.get('is_published'):
            extra['is_published'] = False
        return extra

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._marketplace_normalize_publish(vals) for vals in vals_list]
        if is_manufacturer_portal_user(self.env):
            mine = self._own_manufacturer()
            if not mine:
                raise AccessError(self.env._('Your manufacturer account is not active.'))
            for vals in vals_list:
                vals['manufacturer_id'] = mine.id
                vals['is_published'] = False
                if vals.get('marketplace_approval_state') not in ('not_required', 'pending'):
                    vals['marketplace_approval_state'] = 'pending'
        else:
            is_mgr = self.env.user.has_group('furniture_marketplace.group_marketplace_manager')
            for vals in vals_list:
                vals.update(self.browse()._marketplace_resolve(vals, is_mgr))
        return super().create(vals_list)

    def write(self, vals):
        vals = self._marketplace_normalize_publish(vals)
        if is_manufacturer_portal_user(self.env):
            mine = self._own_manufacturer()
            for rec in self.sudo():
                if not mine or rec.manufacturer_id != mine:
                    raise AccessError(self.env._('You can only modify your own products.'))
            if 'manufacturer_id' in vals and vals['manufacturer_id'] != mine.id:
                raise AccessError(self.env._('You cannot assign a product to another manufacturer.'))
            if vals.get('is_published'):
                raise AccessError(self.env._('Only the platform can publish products.'))
            if vals.get('marketplace_approval_state') in ('approved', 'rejected'):
                raise AccessError(self.env._('Only the platform can approve or reject products.'))
            if vals.get('marketplace_approval_state') == 'pending':
                vals['is_published'] = False
            return super().write(vals)
        if not {'manufacturer_id', 'marketplace_approval_state', 'is_published'} & set(vals):
            return super().write(vals)
        is_mgr = self.env.user.has_group('furniture_marketplace.group_marketplace_manager')
        # group records needing the same extra values -> one write per group
        groups = {}
        for rec in self:
            extra = rec._marketplace_resolve(vals, is_mgr)
            key = tuple(sorted(extra.items()))
            groups[key] = groups.get(key, self.browse()) | rec
        for key, recs in groups.items():
            super(ProductTemplate, recs).write(dict(vals, **dict(key)))
            if dict(key).get('is_published') is False and 'is_published' not in vals:
                for rec in recs:
                    rec.message_post(body=self.env._(
                        'Unpublished from the website: the product is waiting for marketplace approval.'))
        return True

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------
    def _send_marketplace_mail(self, xmlid):
        template = self.env.ref('furniture_marketplace.%s' % xmlid, raise_if_not_found=False)
        for rec in self:
            if template and rec.sudo().manufacturer_id.email:
                template.sudo().send_mail(rec.id, force_send=True)

    def action_submit_marketplace_product(self):
        for rec in self:
            if not rec.manufacturer_id:
                raise UserError(self.env._('Select a manufacturer first.'))
            rec.sudo().write({'marketplace_approval_state': 'pending', 'marketplace_rejection_reason': False})

    def action_approve_marketplace_product(self):
        check_marketplace_manager(self.env)
        auto_publish = self.env['furniture.marketplace.settings'].get_settings().auto_publish_on_approval
        for rec in self:
            if not rec.manufacturer_id or not rec.manufacturer_id.approved:
                raise UserError(self.env._('The manufacturer must be approved/active first.'))
            vals = {'marketplace_approval_state': 'approved', 'marketplace_rejection_reason': False}
            if auto_publish:
                vals['is_published'] = True
            # manager rights were checked above; the marketplace group itself does not grant product write access
            rec.sudo().write(vals)
            rec._send_marketplace_mail('mail_product_approved')

    def action_reject_marketplace_product(self):
        check_marketplace_manager(self.env)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Reject Product'),
            'res_model': 'furniture.reject.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }

    def _do_reject(self, reason):
        check_marketplace_manager(self.env)
        for rec in self:
            rec.sudo().write({'marketplace_approval_state': 'rejected', 'marketplace_rejection_reason': reason,
                              'is_published': False})
            rec._send_marketplace_mail('mail_product_rejected')

    # ------------------------------------------------------------------
    # Helpers used by catalog import and the manufacturer portal
    # ------------------------------------------------------------------
    @api.model
    def _marketplace_type_vals(self):
        fields_map = self._fields
        if 'is_storable' in fields_map:
            return {'type': 'consu', 'is_storable': True}
        return {'detailed_type': 'product'}

    @api.model
    def _marketplace_internal_category(self, path):
        leaf = split_category_path(path)[-1]
        Category = self.env['product.category'].sudo()
        return Category.search([('name', '=', leaf)], limit=1) or Category.create({'name': leaf})

    @api.model
    def _marketplace_public_category(self, path):
        Public = self.env['product.public.category'].sudo()
        parent = Public.browse()
        for part in split_category_path(path):
            cat = Public.search([('name', '=', part), ('parent_id', '=', parent.id or False)], limit=1)
            parent = cat or Public.create({'name': part, 'parent_id': parent.id or False})
        return parent

    def _marketplace_set_quantity(self, qty):
        """Set the on-hand quantity of the (single) variant in the company's main stock location."""
        Quant = self.env['stock.quant'].sudo()
        for rec in self.sudo():
            product = rec.product_variant_id
            if not product:
                continue
            if 'is_storable' in rec._fields and not rec.is_storable:
                rec.is_storable = True
            warehouse = self.env['stock.warehouse'].sudo().search(
                [('company_id', '=', (rec.company_id or self.env.company).id)], limit=1)
            if not warehouse:
                raise UserError(self.env._('No warehouse is configured: stock quantity cannot be set.'))
            quant = Quant.with_context(inventory_mode=True).create({
                'product_id': product.id, 'location_id': warehouse.lot_stock_id.id,
                'inventory_quantity': qty,
            })
            quant.action_apply_inventory()
