# Furniture Marketplace & Manufacturer Portal (Odoo 20)

Multi-manufacturer furniture marketplace on top of standard Odoo **Website / eCommerce / Sales / Inventory / Payment**.

```
Customer cart (products from workshop A + B + C)
        -> one checkout, one payment
        -> one sale.order
        -> every sale.order.line stores its manufacturer (sale.order.line.manufacturer_id)
```
Nothing in the checkout/payment flow is re-implemented; the module only extends it.

## 1. Installation
1. Copy the `furniture_marketplace` folder into a directory of your `addons_path` (or upload the ZIP content there).
2. Restart Odoo, enable developer mode, *Apps -> Update Apps List*.
3. Install **Furniture Marketplace & Manufacturer Portal**. Dependencies (installed automatically):
   `website_sale`, `website_sale_stock`, `sale_management`, `stock`, `portal`, `auth_signup`, `mail`.
4. Configure an **outgoing mail server** (Settings -> Technical -> Outgoing Mail Servers). Invitation and notification e-mails need it.
5. Enable *Settings -> Website -> Customer Account: "Free sign up"* (or invitation only) and enable at least one **payment provider** (Website -> eCommerce -> Payment Providers) for checkout.
6. Upgrade: `odoo-bin -u furniture_marketplace`. Uninstall removes the module data; standard Odoo is untouched.

Run the bundled tests: `odoo-bin -d <db> -i furniture_marketplace --test-tags /furniture_marketplace --stop-after-init`.

## 2. Roles / groups
| Group | Purpose |
|---|---|
| Marketplace: Platform Administrator | Everything incl. *Configuration*; granted to all Odoo Administrators automatically |
| Marketplace: Procurement / Marketplace Manager | Review/approve applications and products, monitor custom requests |
| Marketplace: Manufacturer Portal User | Granted automatically on approval. Own data only (record rules) |
| Customer / public | Standard Odoo portal/public. Own custom requests via record rule |

Isolation is enforced **on the server** (`security/ir.access.csv`: group rows grant access, domain rows limit it to the manufacturer's own records) and again in Python (`product.template.create/write`): a manufacturer cannot touch another workshop's product, change `manufacturer_id`, publish, or approve.

## 3. Workflows
**Manufacturer onboarding** - *Join as a Manufacturer* (`/manufacturer/apply`) -> form + catalog (CSV/XLSX, template provided) -> instant validation with row-level errors -> preview -> *Submit Application* (reference `APP/YYYY/NNNN`, status Pending Approval, confirmation e-mail) -> backend **Requests** menu -> Approve (contact + portal user + invitation + catalog import) or Reject (wizard with reason + e-mail, no account).

**Products** - every imported/created product is `Pending Approval` and *unpublished*. A Manager approves it on the product form (*Marketplace* tab) - optionally auto-published (Configuration -> Product Approval Settings). Publishing an unapproved manufacturer product is blocked by a constraint. Editing a product in the portal sends it back to approval.

**Stock** - catalog quantity / portal quantity is written as an inventory adjustment (`stock.quant`) in the main warehouse stock location; cards show `free_qty` and an out-of-stock state.

**Custom Furniture Request** - `/custom-furniture-request` (login required). Statuses: Draft, Submitted, Under Review, Accepted, Rejected, Quotation Sent, Confirmed, In Production, Completed, Cancelled. The manufacturer (portal) or a Manager reviews/accepts/rejects; a **quotation is created only from an accepted request with an agreed price** (service product *Custom Furniture Manufacturing*). Confirming the sale order moves the request to *Confirmed*.

## 4. Backend menus (Furniture Marketplace app)
Customer View - Manufacturer (manufacturers, catalog uploads, order lines by manufacturer) - Requests (All / Draft / Pending / Approved / Rejected + Custom Furniture Requests) - Products (grouped/filterable by manufacturer) - Configuration (administrators only: manufacturer types, workshop sizes, categories, approval settings, product approval settings, marketplace settings, portal permissions, e-mail templates, security groups).

## 5. Architecture
| Area | Files |
|---|---|
| Models | `furniture.manufacturer`, `.manufacturer.application`, `.custom.request`, `.catalog.import`/`.catalog.line`, `.workshop.size`, `.manufacturer.type`, `.marketplace.settings`; extensions of `product.template` (`manufacturer_id`, approval, specs, stock helpers), `product.public.category` (live counts), `sale.order(.line)` |
| Catalog parser | `tools/catalog_parser.py` (pure Python, CSV + XLSX, no extra dependency) |
| Controllers | `controllers/main.py` (storefront, registration, custom requests), `controllers/portal.py` (manufacturer portal) |
| Templates | `views/website_templates.xml`, `views/portal_templates.xml` |
| Security | `security/groups.xml` (privilege + groups), `security/ir.access.csv` (all ACLs and record-level domains, Odoo 20 `ir.access`) |

Catalog columns: `product_name, category, description, price, quantity, image, specifications` (templates in `static/src/files/`). `category` accepts `Parent / Child` paths (creates website sub-categories). `image` = public http(s) URL (server fetch is SSRF-protected, public addresses only) or the file name of an image uploaded with the catalog.

## 6. Known limitations / things to verify on your instance
* Ported to the Odoo 20 conventions (privilege-based groups, `ir.access.csv` instead of `ir.model.access.csv` and `ir.rule`, `<list>`/`invisible=` views, `self.env._()` translations). It could not be executed in the authoring environment: run the tests and a smoke test after install.
* The product card/detail additions inherit `website_sale.products_item` and `website_sale.product` at the root element (robust against inner layout changes); the add-to-cart button on the marketplace page posts to `/shop/cart/update` - confirm the route signature on your 20.0 build.
* One portal user per manufacturer. No automatic purchase order / split delivery per manufacturer (lines are tagged so you can add it).
* Registration is public: add a captcha (e.g. Cloudflare Turnstile in Website settings) if you get spam; abandoned drafts are purged daily.
