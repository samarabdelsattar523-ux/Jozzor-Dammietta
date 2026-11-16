import base64
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

class FurnitureMarketplaceController(http.Controller):

    @http.route('/furniture-marketplace', type='http', auth='public', website=True, sitemap=True)
    def marketplace_home(self, **kw):
        categories = request.env['product.public.category'].sudo().search([]).filtered(
            lambda c: any(p.website_published and p.marketplace_approval_state == 'approved'
                          for p in c.product_tmpl_ids))
        products = request.env['product.template'].sudo().search([
            ('sale_ok', '=', True), ('website_published', '=', True),
            ('manufacturer_id', '!=', False), ('marketplace_approval_state', '=', 'approved')
        ], limit=16, order='website_sequence, name')
        return request.render('furniture_marketplace.marketplace_home',
                              {'categories': categories, 'products': products})

    @http.route('/manufacturer/apply', type='http', auth='public', website=True,
                methods=['GET', 'POST'], csrf=True)
    def manufacturer_apply(self, **post):
        countries = request.env['res.country'].sudo().search([])
        error = False
        if request.httprequest.method == 'POST':
            try:
                upload = request.httprequest.files.get('catalog_file')
                if not upload:
                    raise UserError(request.env._('Upload a CSV or XLSX catalog.'))
                attachments = []
                for f in request.httprequest.files.getlist('documents'):
                    if f and f.filename:
                        attachments.append(request.env['ir.attachment'].sudo().create({
                            'name': f.filename, 'datas': base64.b64encode(f.read()),
                            'res_model': 'furniture.manufacturer.application'}).id)
                rec = request.env['furniture.manufacturer.application'].sudo().create({
                    'manufacturer_name': post.get('manufacturer_name'),
                    'representative': post.get('representative'), 'email': post.get('email'),
                    'phone': post.get('phone'), 'address': post.get('address'),
                    'country_id': int(post.get('country_id') or 0), 'city': post.get('city'),
                    'workshop_size': post.get('workshop_size'), 'description': post.get('description'),
                    'catalog_file': base64.b64encode(upload.read()), 'catalog_filename': upload.filename,
                    'document_ids': [(6, 0, attachments)]})
                rec.action_submit()
                return request.render('furniture_marketplace.application_thanks', {'application': rec})
            except Exception as exc:
                error = str(exc)
        return request.render('furniture_marketplace.manufacturer_application_form',
                              {'countries': countries, 'error': error})

    @http.route('/custom-furniture-request', type='http', auth='user', website=True,
                methods=['GET', 'POST'], csrf=True)
    def custom_request(self, **post):
        manufacturers = request.env['furniture.manufacturer'].sudo().search([
            ('approved', '=', True), ('active', '=', True)])
        error = False
        if request.httprequest.method == 'POST':
            try:
                image = request.httprequest.files.get('reference_image')
                if not image:
                    raise UserError(request.env._('Upload a reference image.'))
                rec = request.env['furniture.custom.request'].sudo().create({
                    'title': post.get('title'), 'description': post.get('description'),
                    'reference_image': base64.b64encode(image.read()),
                    'reference_image_filename': image.filename,
                    'manufacturer_id': int(post.get('manufacturer_id') or 0),
                    'notes': post.get('notes'), 'partner_id': request.env.user.partner_id.id})
                rec.action_submit()
                return request.render('furniture_marketplace.custom_request_thanks',
                                      {'request_record': rec})
            except Exception as exc:
                error = str(exc)
        return request.render('furniture_marketplace.custom_request_form',
                              {'manufacturers': manufacturers, 'error': error})

    @http.route('/my/furniture-requests', type='http', auth='user', website=True)
    def my_requests(self, **kw):
        records = request.env['furniture.custom.request'].search([
            ('partner_id', 'child_of', request.env.user.partner_id.commercial_partner_id.id)])
        return request.render('furniture_marketplace.portal_my_requests', {'records': records})

    @http.route('/my/furniture-requests/<int:record_id>', type='http', auth='user', website=True)
    def request_detail(self, record_id, **kw):
        rec = request.env['furniture.custom.request'].search([
            ('id', '=', record_id),
            ('partner_id', 'child_of', request.env.user.partner_id.commercial_partner_id.id)], limit=1)
        if not rec:
            return request.not_found()
        return request.render('furniture_marketplace.portal_request_detail', {'record': rec})

    @http.route('/my/manufacturer', type='http', auth='user', website=True)
    def manufacturer_dashboard(self, **kw):
        manufacturer = request.env['furniture.manufacturer'].sudo().search([
            ('user_id', '=', request.env.user.id), ('active', '=', True)], limit=1)
        if not manufacturer:
            return request.not_found()
        products = request.env['product.template'].search([('manufacturer_id', '=', manufacturer.id)])
        requests = request.env['furniture.custom.request'].sudo().search([
            ('manufacturer_id', '=', manufacturer.id)])
        order_lines = request.env['sale.order.line'].sudo().search([
            ('manufacturer_id', '=', manufacturer.id),
            ('order_id.state', 'in', ['sale', 'done']),
        ], order='order_id.date_order desc')
        return request.render('furniture_marketplace.manufacturer_dashboard',
                              {'manufacturer': manufacturer, 'products': products,
                               'custom_requests': requests, 'order_lines': order_lines})


    @http.route('/my/manufacturer/product/create', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def create_manufacturer_product(self, **post):
        manufacturer = request.env['furniture.manufacturer'].sudo().search([
            ('user_id', '=', request.env.user.id), ('active', '=', True)], limit=1)
        if not manufacturer:
            return request.not_found()
        try:
            category = request.env['product.category'].sudo().browse(
                int(post.get('category_id') or 0)).exists()
            vals = {
                'name': post.get('name'),
                'list_price': float(post.get('list_price') or 0),
                'description_sale': post.get('description_sale'),
                'manufacturer_id': manufacturer.id,
                'sale_ok': True,
                'marketplace_approval_state': 'pending',
                'marketplace_submitted_by_manufacturer': True,
                'website_published': False,
            }
            if category:
                vals['categ_id'] = category.id
            request.env['product.template'].sudo().create(vals)
        except Exception as exc:
            return request.render('furniture_marketplace.manufacturer_dashboard', {
                'manufacturer': manufacturer,
                'products': request.env['product.template'].sudo().search([('manufacturer_id', '=', manufacturer.id)]),
                'custom_requests': request.env['furniture.custom.request'].sudo().search([('manufacturer_id', '=', manufacturer.id)]),
                'portal_error': str(exc),
            })
        return request.redirect('/my/manufacturer')

    @http.route('/my/manufacturer/product/submit', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def submit_product(self, **post):
        manufacturer = request.env['furniture.manufacturer'].sudo().search([
            ('user_id', '=', request.env.user.id)], limit=1)
        product = request.env['product.template'].search([
            ('id', '=', int(post.get('product_id') or 0)),
            ('manufacturer_id', '=', manufacturer.id)], limit=1)
        if not product:
            return request.not_found()
        product.action_submit_marketplace_product()
        return request.redirect('/my/manufacturer')
