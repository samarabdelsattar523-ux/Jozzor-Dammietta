# Sandoq - Made in Damietta (Odoo 20 website module)

Adds the `/sandoq` landing page to the Odoo website, ported from the original
Next.js / Tailwind design: hero, searchable and filterable furniture showcase,
makers, brand story and a "list your workshop" call to action.

## Install
1. Copy the `jozzor_dammietta` folder into your Odoo `addons_path`.
2. Restart Odoo, then Apps > Update Apps List.
3. Install **Sandoq - Made in Damietta** (depends only on `website`).
4. Open `/sandoq`. A "Sandoq" menu item is added to the main website menu.

CLI alternative: `odoo-bin -d <db> -i jozzor_dammietta --stop-after-init`

## Make it the homepage
Website > Configuration > Settings > Homepage URL = `/sandoq`.

## Customise
- Products, makers and categories: `controllers/main.py`
- Texts and layout: `views/sandoq_templates.xml`
- Look: `static/src/css/sandoq.css` (everything scoped under `.sq-page`)
- Behaviour (filter, search, favourites, menu): `static/src/js/sandoq.js`
- Standard Odoo header/footer: delete the `no_header` / `no_footer` lines in the template.
- Contact email: replace `hello@sandoq.co` in the template.
