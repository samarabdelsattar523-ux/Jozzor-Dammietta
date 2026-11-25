# -*- coding: utf-8 -*-
import base64
import logging
from urllib.parse import quote

from odoo import _, http
from odoo.http import request

from ..models.allocation import MANUFACTURER_TRANSITIONS
from .main import IMAGE_EXT, _float, _int, read_upload, settings

_logger = logging.getLogger(__name__)

# transitions a manufacturer may trigger on a request assigned to them
REQUEST_ACTIONS = {
    'review': ('submitted', 'action_start_review'),
    'start_production': ('confirmed', 'action_start_production'),
    'complete': ('in_production', 'action_complete'),
}


class FurnitureManufacturerPortal(http.Controller):

    # ------------------------------------------------------------------
    # helpers - every query is filtered by the logged-in user's manufacturer
    # ------------------------------------------------------------------
    def _manufacturer(self):
        return request.env['furniture.manufacturer'].sudo().search(
            [('user_id', '=', request.env.user.id), ('approved', '=', True)], limit=1)

    def _guard(self):
        """Return (manufacturer, redirect_response)."""
        maker = self._manufacturer()
        if not maker:
            return None, request.redirect('/manufacturer/apply')
        return maker, None

    def _back(self, key, message):
        """Redirect to the dashboard with a flash message (URL-encoded)."""
        return request.redirect('/my/manufacturer?%s=%s' % (key, quote(str(message))))

    def _base_values(self, maker, **extra):
        values = {'maker': maker, 'cfg': settings(), 'page_name': 'manufacturer'}
        values.update(extra)
        return values

    def _own_product(self, maker, product_id):
        return request.env['product.template'].sudo().search(
            [('id', '=', _int(product_id)), ('manufacturer_id', '=', maker.id)], limit=1)

    # ------------------------------------------------------------------
    # dashboard
    # ------------------------------------------------------------------
    @http.route('/my/manufacturer', type='http', auth='user', website=True)
    def dashboard(self, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        env = request.env
        products = env['product.template'].sudo().with_context(active_test=False).search(
            [('manufacturer_id', '=', maker.id)], order='id desc')
        requests_ = env['furniture.custom.request'].sudo().search([('manufacturer_id', '=', maker.id)])
        imports = env['furniture.catalog.import'].sudo().search([('manufacturer_id', '=', maker.id)], limit=10)
        pending_count = sum(1 for p in products if p.marketplace_approval_state == 'pending')
        open_orders = env['furniture.order.allocation'].sudo().search_count(
            [('manufacturer_id', '=', maker.id), ('state', 'not in', ('delivered', 'cancelled'))])
        return request.render('furniture_marketplace.manufacturer_dashboard', self._base_values(
            maker, products=products, requests=requests_, imports=imports, pending_count=pending_count,
            open_orders=open_orders,
            notice=kw.get('notice'), error=kw.get('error')))

    # ------------------------------------------------------------------
    # profile
    # ------------------------------------------------------------------
    @http.route('/my/manufacturer/profile', type='http', auth='user', website=True, methods=['GET', 'POST'], csrf=True)
    def profile(self, **post):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        cfg = settings()
        if not cfg.portal_allow_profile_edit:
            return self._back('error', _('Profile editing is disabled.'))
        errors = []
        if request.httprequest.method == 'POST':
            vals = {k: (post.get(k) or '').strip() for k in ('representative', 'address', 'city', 'description')}
            phone = (post.get('phone') or '').strip()
            country = request.env['res.country'].sudo().browse(_int(post.get('country_id'))).exists()
            if not phone:
                errors.append(_('Mobile number is required.'))
            if not vals['city'] or not country:
                errors.append(_('City and country are required.'))
            if not errors:
                # whitelist: name, email, approval flags can NOT be changed from the portal
                maker.write(dict(vals, country_id=country.id))
                maker.partner_id.write({'phone': phone, 'street': vals['address'] or False,
                                        'city': vals['city'], 'country_id': country.id})
                return self._back('notice', _('Profile updated.'))
        return request.render('furniture_marketplace.manufacturer_profile', self._base_values(
            maker, errors=errors, countries=request.env['res.country'].sudo().search([])))

    # ------------------------------------------------------------------
    # products
    # ------------------------------------------------------------------
    def _product_form_values(self, maker, product=None, errors=None, post=None):
        env = request.env
        return self._base_values(
            maker, product=product, errors=errors or [], post=post or {},
            public_categories=env['product.public.category'].sudo().search([]),
            categories=env['product.category'].sudo().search([], order='complete_name'))

    @http.route('/my/manufacturer/product/new', type='http', auth='user', website=True)
    def product_new(self, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        if not settings().portal_allow_product_create:
            return self._back('error', _('Product creation is disabled.'))
        return request.render('furniture_marketplace.manufacturer_product_form', self._product_form_values(maker))

    @http.route('/my/manufacturer/product/<int:product_id>', type='http', auth='user', website=True)
    def product_edit(self, product_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        product = self._own_product(maker, product_id)
        if not product:
            return request.not_found()
        return request.render('furniture_marketplace.manufacturer_product_form',
                              self._product_form_values(maker, product=product))

    @http.route('/my/manufacturer/product/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def product_save(self, product_id=None, **post):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        cfg = settings()
        if not cfg.portal_allow_product_create:
            return self._back('error', _('Product creation is disabled.'))
        Product = request.env['product.template'].sudo()
        product = self._own_product(maker, product_id) if product_id else Product.browse()
        if product_id and not product:
            return request.not_found()  # someone else's product -> never reveal it
        errors = []
        name = (post.get('name') or '').strip()
        description = (post.get('description') or '').strip()
        if not name:
            errors.append(_('Product name is required.'))
        try:
            price = float((post.get('price') or '').replace(',', ''))
            if price < 0:
                raise ValueError
        except ValueError:
            price = 0.0
            errors.append(_('Price must be a positive number.'))
        qty = None
        if cfg.portal_allow_stock_update and (post.get('quantity') or '').strip() != '':
            try:
                qty = float(post['quantity'])
                if qty < 0:
                    raise ValueError
            except ValueError:
                errors.append(_('Quantity must be zero or a positive number.'))
        public_cat = request.env['product.public.category'].sudo().browse(_int(post.get('public_categ_id'))).exists()
        internal_cat = request.env['product.category'].sudo().browse(_int(post.get('categ_id'))).exists()
        if not public_cat:
            errors.append(_('Select a website category.'))
        image = extra = None
        try:
            fname, fdata = read_upload(post.get('image'))
            if fname:
                if not fname.lower().endswith(IMAGE_EXT):
                    errors.append(_('The main image must be PNG, JPG, GIF or WEBP.'))
                else:
                    image = base64.b64encode(fdata).decode()
            extra = []
            for f in request.httprequest.files.getlist('extra_images'):
                n, d = read_upload(f)
                if n:
                    if not n.lower().endswith(IMAGE_EXT):
                        errors.append(_('Image "%s" must be PNG, JPG, GIF or WEBP.', n))
                    else:
                        extra.append((n, base64.b64encode(d).decode()))
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            return request.render('furniture_marketplace.manufacturer_product_form',
                                  self._product_form_values(maker, product or None, errors, post))
        vals = {
            'name': name, 'list_price': price, 'description_sale': description,
            'marketplace_specifications': (post.get('specifications') or '').strip(),
            'public_categ_ids': [(6, 0, [public_cat.id])],
            'categ_id': (internal_cat or Product._marketplace_internal_category(public_cat.name)).id,
            'marketplace_approval_state': 'pending', 'website_published': False,
        }
        if image:
            vals['image_1920'] = image
        if product:
            product.write(vals)  # any edit sends the product back to approval and unpublishes it
        else:
            vals.update(Product._marketplace_type_vals())
            vals.update({'manufacturer_id': maker.id, 'sale_ok': True})
            product = Product.create(vals)
        for n, d in extra:
            request.env['product.image'].sudo().create({'name': n, 'image_1920': d, 'product_tmpl_id': product.id})
        if qty is not None:
            product._marketplace_set_quantity(qty)
        return self._back('notice', _('Product saved and submitted for approval.'))

    @http.route('/my/manufacturer/product/<int:product_id>/submit', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def product_submit(self, product_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        product = self._own_product(maker, product_id)
        if not product:
            return request.not_found()
        if product.marketplace_approval_state in ('not_required', 'rejected'):
            product.action_submit_marketplace_product()
        return self._back('notice', _('Product submitted for approval.'))

    # ------------------------------------------------------------------
    # catalog upload (validate -> preview -> import)
    # ------------------------------------------------------------------
    @http.route('/my/manufacturer/catalog', type='http', auth='user', website=True)
    def catalog_upload_form(self, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        if not settings().portal_allow_catalog_upload:
            return self._back('error', _('Catalog upload is disabled.'))
        return request.render('furniture_marketplace.manufacturer_catalog_upload',
                              self._base_values(maker, errors=[]))

    @http.route('/my/manufacturer/catalog/validate', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def catalog_validate(self, **post):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        if not settings().portal_allow_catalog_upload:
            return self._back('error', _('Catalog upload is disabled.'))
        errors, images = [], []
        name = data = None
        try:
            name, data = read_upload(post.get('catalog'))
            for f in request.httprequest.files.getlist('images'):
                n, d = read_upload(f)
                if n and n.lower().endswith(IMAGE_EXT):
                    images.append((n, d))
        except ValueError as exc:
            errors.append(str(exc))
        if not name:
            errors.append(_('Select a CSV or Excel file.'))
        rec = None
        if name and not errors:
            rec, errors = request.env['furniture.catalog.import']._create_from_upload(name, data, manufacturer=maker)
        if errors:
            return request.render('furniture_marketplace.manufacturer_catalog_upload',
                                  self._base_values(maker, errors=errors))
        att_ids = [request.env['ir.attachment'].sudo().create({
            'name': n, 'raw': d, 'res_model': rec._name, 'res_id': rec.id}).id
            for n, d in images]
        rec.write({'image_attachment_ids': [(6, 0, att_ids)]})
        return request.redirect('/my/manufacturer/catalog/%s' % rec.id)

    def _own_import(self, maker, import_id):
        return request.env['furniture.catalog.import'].sudo().search(
            [('id', '=', _int(import_id)), ('manufacturer_id', '=', maker.id)], limit=1)

    @http.route('/my/manufacturer/catalog/<int:import_id>', type='http', auth='user', website=True)
    def catalog_review(self, import_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        rec = self._own_import(maker, import_id)
        if not rec:
            return request.not_found()
        return request.render('furniture_marketplace.manufacturer_catalog_review',
                              self._base_values(maker, imp=rec))

    @http.route('/my/manufacturer/catalog/<int:import_id>/confirm', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def catalog_confirm(self, import_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        rec = self._own_import(maker, import_id)
        if not rec:
            return request.not_found()
        if not settings().portal_allow_catalog_upload:
            return self._back('error', _('Catalog upload is disabled.'))
        if rec.state == 'draft':
            # runs as the (portal) user: the Product ownership checks stay active
            rec.action_import(maker)
        return self._back('notice', _(
            'Catalog imported: %(n)s product(s) created and submitted for approval.', n=rec.imported_count))

    # ------------------------------------------------------------------
    # custom requests assigned to this manufacturer
    # ------------------------------------------------------------------
    def _own_request(self, maker, req_id):
        return request.env['furniture.custom.request'].sudo().search(
            [('id', '=', _int(req_id)), ('manufacturer_id', '=', maker.id)], limit=1)

    @http.route('/my/manufacturer/request/<int:req_id>', type='http', auth='user', website=True)
    def request_detail(self, req_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        rec = self._own_request(maker, req_id)
        if not rec:
            return request.not_found()
        return request.render('furniture_marketplace.manufacturer_request_detail',
                              self._base_values(maker, req=rec, notice=kw.get('notice'), error=kw.get('error')))

    @http.route('/my/manufacturer/request/<int:req_id>/<string:action>', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def request_action(self, req_id, action, reason=None, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        rec = self._own_request(maker, req_id)
        if not rec or not settings().portal_allow_request_review:
            return request.not_found()
        if action == 'reject':
            if rec.state in ('submitted', 'under_review') and (reason or '').strip():
                rec._do_reject(reason.strip())
            return request.redirect('/my/manufacturer/request/%s' % req_id)
        if action == 'quote':
            price = _float(kw.get('price'))
            if rec.state not in ('submitted', 'under_review') or not price or price <= 0:
                return request.redirect('/my/manufacturer/request/%s?error=%s' % (
                    req_id, quote(_('Enter a unit price greater than zero.'))))
            rec.action_send_quote(price=price, lead_time=max(_int(kw.get('lead_time')), 0),
                                  terms=(kw.get('terms') or '').strip())
            return request.redirect('/my/manufacturer/request/%s' % req_id)
        spec = REQUEST_ACTIONS.get(action)
        if spec and rec.state in spec[0].split(','):
            getattr(rec, spec[1])()
        return request.redirect('/my/manufacturer/request/%s' % req_id)

    # ------------------------------------------------------------------
    # order fulfilment: only this manufacturer's allocations (spec 8.4)
    # ------------------------------------------------------------------
    def _own_allocation(self, maker, alloc_id):
        return request.env['furniture.order.allocation'].sudo().search(
            [('id', '=', _int(alloc_id)), ('manufacturer_id', '=', maker.id)], limit=1)

    @http.route('/my/manufacturer/orders', type='http', auth='user', website=True)
    def orders(self, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        allocations = request.env['furniture.order.allocation'].sudo().search(
            [('manufacturer_id', '=', maker.id)], order='id desc')
        return request.render('furniture_marketplace.manufacturer_orders',
                              self._base_values(maker, allocations=allocations))

    @http.route('/my/manufacturer/order/<int:alloc_id>', type='http', auth='user', website=True)
    def order_detail(self, alloc_id, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        alloc = self._own_allocation(maker, alloc_id)
        if not alloc:
            return request.not_found()
        return request.render('furniture_marketplace.manufacturer_order_detail',
                              self._base_values(maker, alloc=alloc, error=kw.get('error')))

    @http.route('/my/manufacturer/order/<int:alloc_id>/<string:action>', type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def order_action(self, alloc_id, action, note=None, **kw):
        maker, redirect = self._guard()
        if redirect:
            return redirect
        alloc = self._own_allocation(maker, alloc_id)
        if not alloc:
            return request.not_found()
        if action == 'exception':
            if (note or '').strip():
                alloc._report_exception(note.strip())
        elif action in MANUFACTURER_TRANSITIONS and alloc.state == MANUFACTURER_TRANSITIONS[action][0]:
            alloc._manufacturer_transition(action)
        return request.redirect('/my/manufacturer/order/%s' % alloc.id)
