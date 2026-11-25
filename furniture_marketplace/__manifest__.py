# -*- coding: utf-8 -*-
{
    'name': 'Furniture Marketplace & Manufacturer Portal',
    'version': '20.0.4.0.0',
    'category': 'Website/eCommerce',
    'summary': 'Multi-manufacturer furniture marketplace with manufacturer onboarding, '
               'catalog import, product approval and custom furniture requests',
    'description': """
Furniture Marketplace & Manufacturer Portal
===========================================
* Public storefront (categories with live product counts, filters, sorting) on top of Website / eCommerce
* One cart, one checkout, one sales order - every order line is linked to its manufacturer
* Manufacturer registration with validated CSV / Excel catalog and preview
* Approval workflow: contact + portal user + invitation e-mail created automatically
* Manufacturer portal (own profile, products, catalog upload, custom requests)
* Product approval before publication, enforced server-side
* Custom furniture requests with a separate workflow, quotation only after agreement
* Security groups, ACLs and record rules for strict data isolation
""",
    'author': 'Custom Development',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'website_sale_stock', 'sale_management', 'stock',
                'portal', 'auth_signup', 'mail'],
    'data': [
        'security/groups.xml',
        'data/sequences.xml',
        'data/master_data.xml',
        'data/mail_templates.xml',
        'views/config_views.xml',
        'views/manufacturer_views.xml',
        'views/catalog_views.xml',
        'views/application_views.xml',
        'views/custom_request_views.xml',
        'views/product_views.xml',
        'views/sale_views.xml',
        'views/menus.xml',
        'views/website_templates.xml',
        'views/portal_templates.xml',
        'security/ir.access.csv',  # last: refers to groups loaded above
    ],
    'assets': {
        'web.assets_frontend': ['furniture_marketplace/static/src/css/marketplace.css'],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
