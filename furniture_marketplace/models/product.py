from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    manufacturer_id = fields.Many2one('furniture.manufacturer', string='Manufacturer / Workshop',
                                       index=True, tracking=True, ondelete='restrict')
    marketplace_approval_state = fields.Selection([
        ('not_required', 'Not Submitted'), ('pending', 'Pending Approval'),
        ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='not_required', copy=False, tracking=True)
    marketplace_submitted_by_manufacturer = fields.Boolean(default=False, copy=False)
    marketplace_rejection_reason = fields.Text(copy=False, tracking=True)

    def action_submit_marketplace_product(self):
        for rec in self:
            if not rec.manufacturer_id:
                raise ValidationError(self.env._('Assign a manufacturer first.'))
            rec.write({'marketplace_approval_state': 'pending', 'website_published': False,
                       'marketplace_rejection_reason': False})

    def action_approve_marketplace_product(self):
        if not self.env.user.has_group('furniture_marketplace.group_marketplace_manager'):
            raise UserError(self.env._('Only Marketplace Managers can approve products.'))
        for rec in self:
            if rec.marketplace_approval_state != 'pending':
                raise UserError(self.env._('Only pending products can be approved.'))
            rec.marketplace_approval_state = 'approved'

    def action_reject_marketplace_product(self):
        if not self.env.user.has_group('furniture_marketplace.group_marketplace_manager'):
            raise UserError(self.env._('Only Marketplace Managers can reject products.'))
        for rec in self:
            if not rec.marketplace_rejection_reason:
                raise ValidationError(self.env._('Enter a rejection reason.'))
            rec.write({'marketplace_approval_state': 'rejected', 'website_published': False})

    @api.constrains('website_published', 'marketplace_approval_state', 'manufacturer_id')
    def _check_marketplace_published(self):
        for rec in self:
            if rec.manufacturer_id and rec.website_published and rec.marketplace_approval_state != 'approved':
                raise ValidationError(self.env._('Approve a marketplace product before publishing it.'))
