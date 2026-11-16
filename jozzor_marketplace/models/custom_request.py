from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class FurnitureCustomRequest(models.Model):
    _name = 'furniture.custom.request'
    _description = 'Custom Furniture Manufacturing Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'create_date desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    title = fields.Char(required=True, tracking=True)
    description = fields.Text(required=True)
    reference_image = fields.Binary(required=True, attachment=True)
    reference_image_filename = fields.Char()
    manufacturer_id = fields.Many2one('furniture.manufacturer', required=True,
                                       domain=[('approved', '=', True), ('active', '=', True)])
    notes = fields.Text()
    partner_id = fields.Many2one('res.partner', required=True,
                                 default=lambda self: self.env.user.partner_id, index=True)
    request_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Submitted'), ('review', 'Under Review'),
        ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('quotation', 'Quotation Sent'),
        ('confirmed', 'Confirmed'), ('production', 'In Production'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled')],
        default='draft', tracking=True)
    rejection_reason = fields.Text()
    sale_order_id = fields.Many2one('sale.order', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('furniture.custom.request') or 'New'
        return super().create(vals_list)

    def _compute_access_url(self):
        super()._compute_access_url()
        for rec in self:
            rec.access_url = '/my/furniture-requests/%s' % rec.id

    def action_submit(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'submitted'})

    def action_start_review(self):
        self.write({'state': 'review'})

    def action_accept(self):
        self.write({'state': 'accepted'})

    def action_reject(self):
        for rec in self:
            if not rec.rejection_reason:
                raise ValidationError(_('Enter a rejection reason.'))
            rec.state = 'rejected'

    def action_create_quotation(self):
        self.ensure_one()
        if self.state not in ('accepted', 'quotation'):
            raise UserError(_('Accept the request before creating a quotation.'))
        if not self.sale_order_id:
            self.sale_order_id = self.env['sale.order'].create({
                'partner_id': self.partner_id.id, 'origin': self.name,
                'note': _('Custom furniture request: %s\n%s') % (self.title, self.description)})
        self.state = 'quotation'
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order',
                'res_id': self.sale_order_id.id, 'view_mode': 'form'}

    def action_confirm_request(self):
        self.write({'state': 'confirmed'})

    def action_start_production(self):
        self.write({'state': 'production'})

    def action_complete(self):
        self.write({'state': 'completed'})
