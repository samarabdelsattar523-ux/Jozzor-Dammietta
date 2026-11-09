# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class JozoorMarketplaceController(http.Controller):

    @http.route(['/jozoor', '/marketplace'], type='http', auth='public', website=True, sitemap=True)
    def jozoor_landing_page(self, **kwargs):
        makers = request.env['jozoor.maker'].sudo().search([])
        products = request.env['product.template'].sudo().search([
            ('is_jozoor_featured', '=', True),
            ('sale_ok', '=', True)
        ])
        categories = ['All furniture', 'Living room', 'Dining', 'Bedroom', 'Office']
        return request.render('jozoor_marketplace.landing_page_template', {
            'makers': makers,
            'products': products,
            'categories': categories,
        })
