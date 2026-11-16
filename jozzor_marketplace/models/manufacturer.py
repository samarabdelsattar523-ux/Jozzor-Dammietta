from odoo import api, fields, models, _

class FurnitureManufacturer(models.Model):
    _name = 'furniture.manufacturer'
    _description = 'Furniture Manufacturer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(readonly=True, copy=False, default='New')
    partner_id = fields.Many2one('res.partner', ondelete='restrict')
    user_id = fields.Many2one('res.users', readonly=True, copy=False)
    representative = fields.Char()
    email = fields.Char()
    phone = fields.Char()
    address = fields.Text()
    country_id = fields.Many2one('res.country')
    city = fields.Char()
    workshop_size = fields.Selection([
        ('small', 'Small'), ('medium', 'Medium'), ('large', 'Large'),
        ('enterprise', 'Enterprise')])
    description = fields.Text()
    application_id = fields.Many2one('furniture.manufacturer.application', readonly=True)
    product_ids = fields.One2many('product.template', 'manufacturer_id')
    request_ids = fields.One2many('furniture.custom.request', 'manufacturer_id')
    product_count = fields.Integer(compute='_compute_counts')
    request_count = fields.Integer(compute='_compute_counts')
    active = fields.Boolean(default=True)
    approved = fields.Boolean(default=True, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('furniture.manufacturer') or 'New'
        return super().create(vals_list)

    def _compute_counts(self):
        for rec in self:
            rec.product_count = len(rec.product_ids)
            rec.request_count = len(rec.request_ids)

    def action_view_products(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Products'),
                'res_model': 'product.template', 'view_mode': 'list,form',
                'domain': [('manufacturer_id', '=', self.id)]}

    def action_view_requests(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Custom Requests'),
                'res_model': 'furniture.custom.request', 'view_mode': 'list,form',
                'domain': [('manufacturer_id', '=', self.id)]}
