{
'name': 'Furniture Marketplace & Manufacturer Portal',
'version': '20.0.1.0.0',
'category': 'Website/eCommerce',
'summary': 'Furniture marketplace with manufacturer onboarding and product approval',
'author': 'Custom Development',
'license': 'LGPL-3',
'depends': ['website_sale', 'portal', 'stock', 'sale_management', 'mail'],
'data': [
'security/groups.xml', 'security/ir.model.access.csv', 'security/rules.xml',
'data/sequences.xml', 'data/mail_templates.xml',
'views/manufacturer_views.xml', 'views/application_views.xml',
'views/custom_request_views.xml', 'views/product_views.xml',
'views/menus.xml', 'views/website_templates.xml'
],
'assets': {'web.assets_frontend': ['furniture_marketplace/static/src/css/marketplace.css']},
'installable': True, 'application': True, 'auto_install': False
}