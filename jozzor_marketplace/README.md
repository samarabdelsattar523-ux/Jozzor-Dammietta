# Furniture Marketplace & Manufacturer Portal (Odoo 20)

## Install
1. Extract the ZIP so the `furniture_marketplace` directory is inside a custom addons path.
2. Restart Odoo and update the Apps list.
3. Install **Furniture Marketplace & Manufacturer Portal**.
4. Assign the **Marketplace Manager** group to internal reviewers.
5. Configure website, taxes, delivery methods and payment providers using standard Odoo settings.
6. Open `/furniture-marketplace`.

## Included
- Customer marketplace landing page, public product categories and approved/published products.
- Manufacturer registration application, attachments and CSV/XLSX catalog upload.
- Application approval/rejection, manufacturer/contact creation and portal-user provisioning.
- Manufacturer-linked products and moderation workflow.
- Manufacturer portal dashboard, basic product creation, product submission for approval, manufacturer-specific order-line visibility for multi-manufacturer orders and own-record isolation rules.
- Custom furniture request submission, lifecycle and customer portal history.
- Standard Odoo eCommerce cart, checkout, sale orders, stock and payment providers are reused.

## Catalog columns
Required headers: `product_name, category, description, price, quantity`.
Imported products are created in Pending Approval. The supplied quantity is not automatically posted into inventory; inventory staff must validate stock through Odoo inventory adjustments. Product image and specifications columns are not imported in this initial version.

## Scope notes
- Confirmed marketplace model: products from multiple manufacturers can be added to one standard Odoo cart, checked out in one transaction, and recorded in one sale order. Each order line is linked to its manufacturer, and each manufacturer portal dashboard displays only that manufacturer's order lines. Automatic child-order splitting, commissions, settlements, payout ledger, vendor-specific delivery charges and stock routing are not implemented because their business rules were not supplied.
- The custom request quotation action creates a draft quotation shell; a sales user must add priced lines and agree delivery/payment terms before sending.
- Workshop size choices are currently Small, Medium, Large and Enterprise.
- The addon uses standard Odoo payment providers; no custom payment gateway is included.

## Validation
Python syntax, XML well-formedness, manifest structure and ZIP layout were checked. A live Odoo 20 installation/runtime test was not possible here. Install on a staging Odoo 20 database and complete functional/security testing before production.
