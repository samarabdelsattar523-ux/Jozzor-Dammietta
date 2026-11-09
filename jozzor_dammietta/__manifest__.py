{
    "name": "Sandoq - Made in Damietta",
    "version": "20.0.1.0.0",
    "category": "Website/Website",
    "summary": "Handcrafted Damietta furniture landing page for the Odoo website",
    "description": """
Sandoq - Made in Damietta
=========================
Adds the /sandoq landing page to the Odoo website: hero, searchable and
filterable furniture showcase, makers, brand story and a call to action
for workshops. Ported from the original Next.js / Tailwind design.
    """,
    "author": "Jozoor Damietta",
    "license": "LGPL-3",
    "depends": ["website"],
    "data": [
        "views/sandoq_templates.xml",
        "data/website_menu.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "jozzor_dammietta/static/src/css/sandoq.css",
            "jozzor_dammietta/static/src/js/sandoq.js",
        ],
    },
    "installable": True,
    "application": False,
}
