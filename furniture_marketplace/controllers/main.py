# -*- coding: utf-8 -*-
import base64
import hmac
import logging
import re

from odoo import _, http
from odoo.fields import Domain
from odoo.http import request

_logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
MAX_UPLOAD = 15 * 1024 * 1024
SORTS = {
    'newest': ('Newest', 'create_date desc, id desc'),
    'price_asc': ('Price: low to high', 'list_price asc, id'),
    'price_desc': ('Price: high to low', 'list_price desc, id'),
    'name': ('Name (A-Z)', 'name asc, id'),
}

def _translated_sorts():
    return {
        'newest': (_('Newest'), 'create_date desc, id desc'),
        'price_asc': (_('Price: low to high'), 'list_price asc, id'),
        'price_desc': (_('Price: high to low'), 'list_price desc, id'),
        'name': (_('Name (A-Z)'), 'name asc, id'),
    }


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_upload(file_storage, max_size=MAX_UPLOAD):
    """-> (filename, bytes) or (None, None). Raises ValueError when too big."""
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None, None
    try:
        file_storage.seek(0)
    except Exception:
        pass
    data = file_storage.read()
    if len(data) > max_size:
        raise ValueError(_('"%s" is larger than %d MB.', file_storage.filename, max_size // 1024 // 1024))
    return file_storage.filename, data


def settings():
    return request.env['furniture.marketplace.settings'].sudo().get_settings()


class FurnitureMarketplaceController(http.Controller):

    # ------------------------------------------------------------------
    # A/B. Storefront
    # ------------------------------------------------------------------
    @http.route(['/furniture-marketplace', '/furniture-marketplace/page/<int:page>'],
                type='http', auth='public', website=True, sitemap=True)
    def marketplace_home(self, page=1, q='', category=None, manufacturer=None, sort='newest',
                         in_stock=None, **kw):
        website = request.env.website  # current website (Odoo 20: from the request context)
        Product = request.env['product.template'].sudo()
        step = max(settings().products_per_page or 12, 1)
        domain = Domain(Product._marketplace_visible_domain()) & website.website_domain()
        category_id, manufacturer_id = _int(category), _int(manufacturer)
        if q:
            domain &= Domain.OR([Domain('name', 'ilike', q), Domain('description_sale', 'ilike', q)])
        if category_id:
            domain &= Domain('public_categ_ids', 'child_of', category_id)
        if manufacturer_id:
            domain &= Domain('manufacturer_id', '=', manufacturer_id)
        if in_stock:
            domain &= Domain('qty_available', '>', 0)
        sort = sort if sort in SORTS else 'newest'
        total = Product.search_count(domain)
        url_args = {k: v for k, v in {'q': q, 'category': category_id or None,
                                       'manufacturer': manufacturer_id or None,
                                       'sort': sort, 'in_stock': in_stock}.items() if v}
        pager = website.pager(url='/furniture-marketplace', total=total, page=page,
                                      step=step, scope=5, url_args=url_args)
        products = Product.search(domain, order=SORTS[sort][1], limit=step, offset=pager['offset'])
        Public = request.env['product.public.category'].sudo()
        values = {
            'categories': Public.search([('parent_id', '=', False)], order='sequence, name'),
            'all_categories': Public.search([]),  # model default order: sequence, name
            'products': products,
            'manufacturers': request.env['furniture.manufacturer'].sudo().search([('approved', '=', True)]),
            'pager': pager,
            'search': q, 'current_category': Public.browse(category_id).exists(),
            'current_manufacturer': manufacturer_id, 'sort': sort, 'sorts': _translated_sorts(),
            'in_stock': bool(in_stock), 'total': total,
        }
        return request.render('furniture_marketplace.marketplace_home', values)

    # ------------------------------------------------------------------
    # 4. Manufacturer registration (validate -> preview -> submit)
    # ------------------------------------------------------------------
    def _apply_context(self, values=None, errors=None):
        env = request.env
        ctx = {
            'countries': env['res.country'].sudo().search([]),
            'sizes': env['furniture.workshop.size'].sudo().search([]),
            'values': values or {}, 'errors': errors or [],
        }
        return ctx

    @http.route('/manufacturer/apply', type='http', auth='public', website=True, sitemap=True)
    def manufacturer_apply(self, **kw):
        return request.render('furniture_marketplace.manufacturer_apply', self._apply_context())

    @http.route('/manufacturer/apply/validate', type='http', auth='public', website=True,
                methods=['POST'], csrf=True)
    def manufacturer_apply_validate(self, **post):
        env = request.env
        errors = []
        required = {
            'manufacturer_name': _('Manufacturer / Workshop name'), 'representative': _('Owner / Representative'),
            'email': _('Email'), 'phone': _('Mobile number'),
            'country_id': _('Country'), 'city': _('City'), 'workshop_size_id': _('Workshop size'),
        }
        for key, label in required.items():
            if not (post.get(key) or '').strip():
                errors.append(_('%s is required.', label))
        email = (post.get('email') or '').strip()
        if email and not EMAIL_RE.match(email):
            errors.append(_('The e-mail address is not valid.'))
        country = env['res.country'].sudo().browse(_int(post.get('country_id'))).exists()
        size = env['furniture.workshop.size'].sudo().browse(_int(post.get('workshop_size_id'))).exists()
        if post.get('country_id') and not country:
            errors.append(_('Select a valid country.'))
        if post.get('workshop_size_id') and not size:
            errors.append(_('Select a valid workshop size.'))
        if email and env['furniture.manufacturer.application'].sudo().search_count(
                [('email', '=ilike', email), ('state', '=', 'submitted')]):
            errors.append(_('An application with this e-mail is already pending approval.'))

        catalog_name = catalog_raw = None
        documents, images = [], []
        try:
            catalog_file = post.get('catalog') or request.httprequest.files.get('catalog')
            catalog_name, catalog_raw = read_upload(catalog_file)
            for f in request.httprequest.files.getlist('documents'):
                name, data = read_upload(f)
                if name:
                    documents.append((name, data))
            for f in request.httprequest.files.getlist('images'):
                name, data = read_upload(f)
                if name:
                    if not name.lower().endswith(IMAGE_EXT):
                        errors.append(_('Product image "%s" must be PNG, JPG, GIF or WEBP.', name))
                    else:
                        images.append((name, data))
        except ValueError as exc:
            errors.append(str(exc))
        if not catalog_name:
            errors.append(_('The product catalog file (Excel or CSV) is required.'))

        catalog = None
        if catalog_name and not errors:
            catalog, file_errors = env['furniture.catalog.import']._create_from_upload(catalog_name, catalog_raw)
            errors.extend(file_errors)
        elif catalog_name:  # also validate the file so every problem is shown at once
            _rows, file_errors = env['furniture.catalog.import']._validate_only(catalog_name, catalog_raw)
            errors.extend(file_errors)
        if errors:
            if catalog:  # created but other errors appeared -> discard
                catalog.sudo().unlink()
            return request.render('furniture_marketplace.manufacturer_apply',
                                  self._apply_context(post, errors))

        application = env['furniture.manufacturer.application'].sudo().create({
            'manufacturer_name': post['manufacturer_name'].strip(), 'representative': post['representative'].strip(),
            'email': email, 'phone': post['phone'].strip(), 'address': (post.get('address') or '').strip(),
            'country_id': country.id, 'city': post['city'].strip(), 'workshop_size_id': size.id,
            'description': (post.get('description') or '').strip(), 'from_website': True,
            'catalog_import_id': catalog.id,
        })
        catalog.write({'application_id': application.id})
        Attachment = env['ir.attachment'].sudo()
        doc_ids = []
        for name, data in documents + images:
            att = Attachment.create({'name': name, 'datas': base64.b64encode(data),
                                     'res_model': application._name, 'res_id': application.id})
            doc_ids.append(att.id)
        application.write({'document_ids': [(6, 0, doc_ids)]})
        return request.redirect('/manufacturer/apply/review/%s/%s' % (application.id, application.access_token))

    def _get_draft_application(self, app_id, token):
        app = request.env['furniture.manufacturer.application'].sudo().browse(_int(app_id)).exists()
        if not app or not token or not hmac.compare_digest(app.access_token or '', token):
            return None
        return app

    @http.route('/manufacturer/apply/review/<int:app_id>/<string:token>', type='http', auth='public', website=True)
    def manufacturer_apply_review(self, app_id, token, **kw):
        app = self._get_draft_application(app_id, token)
        if not app or app.state != 'draft':
            return request.redirect('/manufacturer/apply')
        return request.render('furniture_marketplace.manufacturer_apply_review', {'application': app})

    @http.route('/manufacturer/apply/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def manufacturer_apply_submit(self, app_id=None, token=None, **kw):
        app = self._get_draft_application(app_id, token)
        if not app:
            return request.redirect('/manufacturer/apply')
        app.action_submit()
        return request.render('furniture_marketplace.manufacturer_apply_thanks', {'application': app})

    # ------------------------------------------------------------------
    # 3. Custom furniture request (customers)
    # ------------------------------------------------------------------
    def _request_form_context(self, values=None, errors=None):
        return {
            'manufacturers': request.env['furniture.manufacturer'].sudo().search([('approved', '=', True)]),
            'partner': request.env.user.partner_id, 'values': values or {}, 'errors': errors or [],
        }

    @http.route('/custom-furniture-request', type='http', auth='user', website=True)
    def custom_request_form(self, **kw):
        return request.render('furniture_marketplace.custom_request_form', self._request_form_context())

    @http.route('/custom-furniture-request/submit', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def custom_request_submit(self, **post):
        env = request.env
        errors = []
        title, description = (post.get('title') or '').strip(), (post.get('description') or '').strip()
        if not title:
            errors.append(_('Request title is required.'))
        if not description:
            errors.append(_('Furniture description is required.'))
        maker = env['furniture.manufacturer'].sudo().search(
            [('id', '=', _int(post.get('manufacturer_id'))), ('approved', '=', True)], limit=1)
        if not maker:
            errors.append(_('Select a preferred manufacturer from the list.'))
        name = data = None
        try:
            name, data = read_upload(post.get('reference_image'))
        except ValueError as exc:
            errors.append(str(exc))
        if not name:
            errors.append(_('A reference image is required.'))
        elif not name.lower().endswith(IMAGE_EXT):
            errors.append(_('The reference must be a PNG, JPG, GIF or WEBP image.'))
        if errors:
            return request.render('furniture_marketplace.custom_request_form',
                                  self._request_form_context(post, errors))
        rec = env['furniture.custom.request'].sudo().create({
            'title': title, 'description': description, 'notes': (post.get('notes') or '').strip(),
            'manufacturer_id': maker.id, 'partner_id': env.user.partner_id.id,
            'reference_image': base64.b64encode(data), 'reference_image_name': name,
        })
        rec.action_submit()
        return request.redirect('/my/furniture-requests/%s?submitted=1' % rec.id)

    # ------------------------------------------------------------------
    # Customer portal: own requests
    # ------------------------------------------------------------------
    def _customer_requests_domain(self):
        return [('partner_id', 'child_of', [request.env.user.partner_id.commercial_partner_id.id])]

    @http.route('/my/furniture-requests', type='http', auth='user', website=True)
    def my_requests(self, **kw):
        recs = request.env['furniture.custom.request'].sudo().search(self._customer_requests_domain())
        return request.render('furniture_marketplace.my_requests', {'requests': recs, 'page_name': 'furniture_requests'})

    @http.route('/my/furniture-requests/<int:req_id>', type='http', auth='user', website=True)
    def my_request_detail(self, req_id, submitted=None, **kw):
        rec = request.env['furniture.custom.request'].sudo().search(
            self._customer_requests_domain() + [('id', '=', req_id)], limit=1)
        if not rec:
            return request.not_found()
        order_url = rec.sale_order_id.get_portal_url() if rec.sale_order_id else False
        return request.render('furniture_marketplace.my_request_detail', {
            'req': rec, 'submitted': bool(submitted), 'order_url': order_url,
            'can_cancel': settings().customer_allow_request_cancel and rec.state in ('draft', 'submitted'),
            'page_name': 'furniture_requests'})

    @http.route('/my/furniture-requests/<int:req_id>/cancel', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def my_request_cancel(self, req_id, **kw):
        rec = request.env['furniture.custom.request'].sudo().search(
            self._customer_requests_domain() + [('id', '=', req_id)], limit=1)
        if rec and settings().customer_allow_request_cancel and rec.state in ('draft', 'submitted'):
            rec.action_cancel()
        return request.redirect('/my/furniture-requests/%s' % req_id)
