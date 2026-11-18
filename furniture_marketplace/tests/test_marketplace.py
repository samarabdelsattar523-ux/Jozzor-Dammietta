# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

CSV = (b"product_name,category,description,price,quantity,image,specifications\n"
       b"Oak Table,Dining / Tables,Solid oak,500,4,,Material: Oak\n"
       b"Chair,Dining / Chairs,Wood chair,80,10,,Material: Beech\n")


@tagged('post_install', '-at_install')
class TestFurnitureMarketplace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['res.users'].create({
            'name': 'Marketplace Manager', 'login': 'fm_manager@example.com',
            'group_ids': [(6, 0, [cls.env.ref('furniture_marketplace.group_marketplace_manager').id])],
        })

    def _application(self, email, name):
        catalog, errors = self.env['furniture.catalog.import']._create_from_upload('c.csv', CSV)
        self.assertFalse(errors)
        app = self.env['furniture.manufacturer.application'].create({
            'manufacturer_name': name, 'representative': 'Owner', 'email': email, 'phone': '123',
            'address': 'Street 1', 'country_id': self.env.ref('base.us').id, 'city': 'Austin',
            'workshop_size_id': self.env.ref('furniture_marketplace.workshop_size_small').id,
            'catalog_import_id': catalog.id,
        })
        catalog.application_id = app
        return app

    def _approved(self, email, name):
        app = self._application(email, name)
        app.action_submit()
        app.with_user(self.manager).action_approve()
        return app.manufacturer_id

    def test_catalog_validation_errors(self):
        _rec, errors = self.env['furniture.catalog.import']._create_from_upload(
            'bad.csv', b"product_name,category,description,price,quantity\n,,x,abc,-1\n")
        self.assertTrue(errors)
        _rec, errors = self.env['furniture.catalog.import']._create_from_upload('x.csv', b"a,b\n1,2\n")
        self.assertIn('Missing required', errors[0])

    def test_category_path_never_crashes(self):
        # a degenerate path used to raise IndexError inside the catalog import
        Product = self.env['product.template']
        self.assertTrue(Product._marketplace_internal_category('///'))
        self.assertTrue(Product._marketplace_public_category(' / '))

    def test_internal_user_can_read_marketplace_config(self):
        # ACL rows must exist for internal users, not only for sudo() code paths
        internal = self.env['res.users'].create({
            'name': 'Internal Staff', 'login': 'fm_internal@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])]})
        self.env['furniture.workshop.size'].with_user(internal).search([], limit=1)
        self.env['furniture.manufacturer.type'].with_user(internal).search([], limit=1)
        self.env['furniture.catalog.import'].with_user(internal).search([], limit=1)
        with self.assertRaises(AccessError):
            self.env['furniture.marketplace.settings'].with_user(internal).search([], limit=1)

    def test_approval_creates_user_manufacturer_and_pending_products(self):
        app = self._application('maker1@example.com', 'Maker One')
        self.assertTrue(app.name.startswith('APP/'))
        app.action_submit()
        self.assertEqual(app.state, 'submitted')
        app.with_user(self.manager).action_approve()
        self.assertEqual(app.state, 'approved')
        maker = app.manufacturer_id
        self.assertTrue(maker.user_id.share)
        self.assertTrue(maker.user_id.has_group('furniture_marketplace.group_manufacturer_portal'))
        self.assertEqual(len(maker.product_ids), 2)
        for product in maker.product_ids:
            self.assertEqual(product.marketplace_approval_state, 'pending')
            self.assertFalse(product.website_published)

    def test_only_managers_can_approve(self):
        app = self._application('maker2@example.com', 'Maker Two')
        app.action_submit()
        portal = self.env['res.users'].create({
            'name': 'Random', 'login': 'rnd@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        with self.assertRaises(AccessError):
            app.with_user(portal).action_approve()

    def test_reject_creates_no_user(self):
        app = self._application('maker3@example.com', 'Maker Three')
        app.action_submit()
        app.with_user(self.manager)._do_reject('Incomplete documents')
        self.assertEqual(app.state, 'rejected')
        self.assertFalse(self.env['res.users'].with_context(active_test=False).search(
            [('login', '=', 'maker3@example.com')]))

    def test_product_cannot_be_published_before_approval(self):
        maker = self._approved('maker4@example.com', 'Maker Four')
        product = maker.product_ids[0]
        with self.assertRaises(ValidationError):
            product.write({'website_published': True})
        product.with_user(self.manager).action_approve_marketplace_product()
        product.write({'website_published': True})
        self.assertIn(product, self.env['product.template'].search(
            self.env['product.template']._marketplace_visible_domain()))

    def test_manufacturer_isolation(self):
        maker_a = self._approved('a@example.com', 'Maker A')
        maker_b = self._approved('b@example.com', 'Maker B')
        user_a = maker_a.user_id
        foreign = maker_b.product_ids[0]
        with self.assertRaises(AccessError):
            foreign.with_user(user_a).write({'name': 'hacked'})
        own = maker_a.product_ids[0]
        with self.assertRaises(AccessError):
            own.with_user(user_a).write({'manufacturer_id': maker_b.id})
        with self.assertRaises(AccessError):
            own.with_user(user_a).write({'website_published': True})
        created = self.env['product.template'].with_user(user_a).create(
            {'name': 'Mine', 'manufacturer_id': maker_b.id})
        self.assertEqual(created.sudo().manufacturer_id, maker_a)  # forced to the caller's own company
        self.assertFalse(created.sudo().website_published)

    def test_custom_request_flow(self):
        maker = self._approved('maker5@example.com', 'Maker Five')
        customer = self.env['res.partner'].create({'name': 'Customer', 'email': 'cust@example.com'})
        req = self.env['furniture.custom.request'].create({
            'title': 'Desk', 'description': 'Custom desk', 'partner_id': customer.id,
            'manufacturer_id': maker.id, 'reference_image': 'R0lGODlhAQABAAAAACw=',
        })
        req.action_submit()
        req.action_accept()
        with self.assertRaises(UserError):
            req.with_user(self.manager).action_create_quotation()  # no agreed price yet
        req.agreed_price = 900.0
        req.with_user(self.manager).action_create_quotation()
        self.assertEqual(req.state, 'quotation')
        req.sale_order_id.action_confirm()
        self.assertEqual(req.state, 'confirmed')
