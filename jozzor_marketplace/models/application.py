import base64, csv, io, zipfile, xml.etree.ElementTree as ET
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class FurnitureManufacturerApplication(models.Model):
    _name = 'furniture.manufacturer.application'
    _description = 'Manufacturer Registration Application'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    manufacturer_name = fields.Char(required=True, tracking=True)
    representative = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char(required=True)
    address = fields.Text(required=True)
    country_id = fields.Many2one('res.country', required=True)
    city = fields.Char(required=True)
    workshop_size = fields.Selection([
        ('small', 'Small'), ('medium', 'Medium'), ('large', 'Large'),
        ('enterprise', 'Enterprise')], required=True)
    description = fields.Text()
    catalog_file = fields.Binary(required=True, attachment=True)
    catalog_filename = fields.Char(required=True)
    document_ids = fields.Many2many('ir.attachment', 'furniture_application_attachment_rel',
                                    'application_id', 'attachment_id')
    state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Pending Approval'),
        ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='draft', required=True, tracking=True)
    rejection_reason = fields.Text(tracking=True)
    internal_notes = fields.Text()
    manufacturer_id = fields.Many2one('furniture.manufacturer', readonly=True, copy=False)
    submitted_on = fields.Datetime(readonly=True)
    imported_product_ids = fields.Many2many('product.template', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('furniture.manufacturer.application') or 'New'
        return super().create(vals_list)

    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            rec.write({'state': 'submitted', 'submitted_on': fields.Datetime.now()})
            rec._send_mail('furniture_marketplace.mail_application_received')

    def action_approve(self):
        if not self.env.user.has_group('furniture_marketplace.group_marketplace_manager'):
            raise UserError(_('Only Marketplace Managers can approve applications.'))
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only pending applications can be approved.'))
            partner = self.env['res.partner'].search([('email', '=', rec.email)], limit=1)
            pvals = {'name': rec.manufacturer_name, 'email': rec.email, 'phone': rec.phone,
                     'street': rec.address, 'city': rec.city, 'country_id': rec.country_id.id,
                     'company_type': 'company'}
            if partner:
                partner.write(pvals)
            else:
                partner = self.env['res.partner'].create(pvals)
            manufacturer = self.env['furniture.manufacturer'].create({
                'name': rec.manufacturer_name, 'partner_id': partner.id,
                'representative': rec.representative, 'email': rec.email,
                'phone': rec.phone, 'address': rec.address, 'country_id': rec.country_id.id,
                'city': rec.city, 'workshop_size': rec.workshop_size,
                'description': rec.description, 'application_id': rec.id})
            portal_group = self.env.ref('furniture_marketplace.group_manufacturer_portal')
            user = self.env['res.users'].sudo().search([('login', '=', rec.email)], limit=1)
            if user:
                if user.partner_id != partner:
                    raise UserError(_('This login already belongs to another contact.'))
                user.sudo().write({'groups_id': [(4, portal_group.id)]})
            else:
                user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
                    'name': rec.representative, 'login': rec.email, 'email': rec.email,
                    'partner_id': partner.id, 'groups_id': [(6, 0, [portal_group.id])]})
            manufacturer.user_id = user.id
            rec.write({'manufacturer_id': manufacturer.id, 'state': 'approved'})
            try:
                user.action_reset_password()
            except Exception:
                rec.message_post(body=_('Portal account created. Resend the password invitation from the user record if needed.'))
            rec._import_catalog(manufacturer)
            rec._send_mail('furniture_marketplace.mail_application_approved')

    def action_reject(self):
        if not self.env.user.has_group('furniture_marketplace.group_marketplace_manager'):
            raise UserError(_('Only Marketplace Managers can reject applications.'))
        for rec in self:
            if not rec.rejection_reason:
                raise ValidationError(_('Enter a rejection reason before rejecting.'))
            rec.state = 'rejected'
            rec._send_mail('furniture_marketplace.mail_application_rejected')

    def _send_mail(self, xmlid):
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template and self.email:
            template.sudo().send_mail(self.id, force_send=True)

    def _read_xlsx(self, raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                root = ET.fromstring(z.read('xl/sharedStrings.xml'))
                ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                strings = [''.join(t.text or '' for t in si.findall('.//x:t', ns))
                           for si in root.findall('x:si', ns)]
            root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            rows = []
            for row in root.findall('.//x:sheetData/x:row', ns):
                vals = []
                for cell in row.findall('x:c', ns):
                    v = cell.find('x:v', ns)
                    val = v.text if v is not None else ''
                    if cell.get('t') == 's' and val:
                        val = strings[int(val)]
                    vals.append(val)
                rows.append(vals)
        if not rows:
            return []
        headers = [str(v).strip().lower().replace(' ', '_') for v in rows[0]]
        return [dict(zip(headers, row)) for row in rows[1:] if any(row)]

    def _import_catalog(self, manufacturer):
        self.ensure_one()
        raw = base64.b64decode(self.catalog_file or b'')
        filename = (self.catalog_filename or '').lower()
        try:
            if filename.endswith('.csv'):
                rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                rows = [{str(k).strip().lower().replace(' ', '_'): v for k, v in r.items()} for r in rows]
            elif filename.endswith('.xlsx'):
                rows = self._read_xlsx(raw)
            else:
                raise UserError(_('Only CSV and XLSX files are supported.'))
            required = {'product_name', 'category', 'description', 'price', 'quantity'}
            if not rows:
                raise UserError(_('No product rows were found.'))
            missing = required - set(rows[0])
            if missing:
                raise UserError(_('Missing columns: %s') % ', '.join(sorted(missing)))
        except Exception as exc:
            self.message_post(body=_('Catalog import was not completed: %s') % str(exc))
            return
        created = self.env['product.template']
        for row_no, row in enumerate(rows, start=2):
            try:
                title = str(row.get('product_name') or '').strip()
                if not title:
                    raise ValueError(_('Product name is required.'))
                category_name = str(row.get('category') or '').strip()
                category = self.env['product.category'].search([('name', '=', category_name)], limit=1)
                if category_name and not category:
                    category = self.env['product.category'].create({'name': category_name})
                product = self.env['product.template'].create({
                    'name': title, 'detailed_type': 'product', 'sale_ok': True,
                    'list_price': float(row.get('price') or 0),
                    'categ_id': category.id if category else False,
                    'description_sale': str(row.get('description') or ''),
                    'manufacturer_id': manufacturer.id,
                    'marketplace_approval_state': 'pending',
                    'marketplace_submitted_by_manufacturer': True})
                created |= product
            except Exception as exc:
                self.message_post(body=_('Catalog row %s skipped: %s') % (row_no, str(exc)))
        self.imported_product_ids = [(6, 0, created.ids)]
        self.message_post(body=_('%s products imported as Pending Approval. Quantity values are not posted to inventory.') % len(created))
