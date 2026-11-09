# -*- coding: utf-8 -*-
{
    'name': 'Jozoor Damietta Marketplace',
    'version': '20.0.1.0.0',
    'summary': 'Handcrafted furniture marketplace connecting Damietta makers with clients',
    'description': '''
        Jozoor Damietta Furniture Marketplace Platform
        =============================================
        - Showcase handcrafted furniture pieces from independent Damietta workshops.
        - Directory of verified makers with locations, ratings, and portfolios.
        - Public marketplace portal with live filtering, room categories, and instant cart integration.
    ''',
    'category': 'Website/eCommerce',
    'author': 'Jozoor Damietta',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'web',
        'website',
        'sale',
        'product',
    ],
    'data': [
        'security/ir.access.csv',
        'views/marketplace_maker_views.xml',
        'views/product_template_views.xml',
        'views/marketplace_templates.xml',
        'views/menu_views.xml',
        'data/initial_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'jozoor_marketplace/static/src/css/marketplace.css',
            'jozoor_marketplace/static/src/js/marketplace.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
