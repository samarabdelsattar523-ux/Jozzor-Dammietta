# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError

ALLOWED = ('furniture.manufacturer.application', 'furniture.custom.request', 'product.template')


class FurnitureRejectWizard(models.TransientModel):
    _name = 'furniture.reject.wizard'
    _description = 'Rejection Reason'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    reason = fields.Text('Rejection Reason', required=True)

    def action_confirm(self):
        self.ensure_one()
        if self.res_model not in ALLOWED:
            raise UserError(self.env._('Unsupported record type.'))
        self.env[self.res_model].browse(self.res_id)._do_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
