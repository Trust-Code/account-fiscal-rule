# -*- encoding: utf-8 -*-
##############################################################################
#
#    Account Product - Fiscal Classification module for Odoo
#    Copyright (C) 2014 -Today GRAP (http://www.grap.coop)
#    @author Sylvain LE GAL (https://twitter.com/legalsylvain)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import logging

from openerp import SUPERUSER_ID, models, fields, api, _
from openerp.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountProductFiscalClassification(models.Model):
    """Fiscal Classification of customer and supplier taxes.
    This classification is linked to a product to select a bundle of taxes
     in one time."""
    _name = 'account.product.fiscal.classification'
    _description = 'Product Fiscal Classification'
    _MAX_LENGTH_NAME = 256

    # Getter / Setter Section
    def _default_company_id(self):
        return self.env['res.users']._get_company()

    def _get_product_tmpl_qty(self):
        for rec in self:
            rec.product_tmpl_qty = self.env['product.template'].search_count([
                ('fiscal_classification_id', '=', rec.id), '|',
                ('active', '=', False), ('active', '=', True)])

    def _get_product_tmpl_ids(self):
        for rec in self:
            rec.product_tmpl_ids = self.env['product.template'].search([
                ('fiscal_classification_id', '=', rec.id), '|',
                ('active', '=', False), ('active', '=', True)])

    # Field Section
    name = fields.Char(
        size=_MAX_LENGTH_NAME, required=True, select=True)

    company_id = fields.Many2one(
        comodel_name='res.company', default=_default_company_id,
        string='Company', help="Specify a company"
        " if you want to define this Fiscal Classification only for specific"
        " company. Otherwise, this Fiscal Classification will be available"
        " for all companies.")

    active = fields.Boolean(
        default=True,
        help="If unchecked, it will allow you to hide the Fiscal"
        " Classification without removing it.")

    product_tmpl_ids = fields.One2many(
        comodel_name='product.template', string='Products',
        compute=_get_product_tmpl_ids)

    product_tmpl_qty = fields.Integer(
        string='Products Quantity', compute=_get_product_tmpl_qty)

    purchase_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='fiscal_classification_purchase_tax_rel',
        column1='fiscal_classification_id', column2='tax_id',
        string='Purchase Taxes', oldname="purchase_base_tax_ids", domain="""[
            ('parent_id', '=', False),
            ('type_tax_use', 'in', ['purchase', 'all'])]""")

    sale_tax_ids = fields.Many2many(
        comodel_name='account.tax',
        relation='fiscal_classification_sale_tax_rel',
        column1='fiscal_classification_id', column2='tax_id',
        string='Sale Taxes', oldname="sale_base_tax_ids", domain="""[
            ('parent_id', '=', False),
            ('type_tax_use', 'in', ['sale', 'all'])]""")

    # Overload Section
    @api.multi
    def write(self, vals):
        res = super(AccountProductFiscalClassification, self).write(vals)
        pt_obj = self.env['product.template']
        if 'supplier_tax_ids' in vals or 'customer_tax_ids' in vals:
            for fc in self:
                pt_lst = pt_obj.browse([x.id for x in fc.product_tmpl_ids])
                pt_lst.write({'fiscal_classification_id': fc.id})
        return res

    @api.multi
    def unlink(self):
        for fc in self:
            if fc.product_tmpl_qty != 0:
                raise ValidationError(_(
                    "You cannot delete The Fiscal Classification '%s' because"
                    " it contents %s products. Please move products"
                    " to another Fiscal Classification first.") % (
                        fc.name, fc.product_tmpl_qty))
        return super(AccountProductFiscalClassification, self).unlink()

    # Custom Sections
    @api.model
    def find_or_create(self, company_id, sale_tax_ids, purchase_tax_ids):
        at_obj = self.env['account.tax']
        # Search for existing Fiscal Classification

        fcs = self.search(
            ['|', ('active', '=', False), ('active', '=', True)])

        for fc in fcs:
            if (
                    fc.company_id.id == company_id
                    and sorted(fc.sale_tax_ids.ids) ==
                    sorted(sale_tax_ids)
                    and sorted(fc.purchase_tax_ids.ids) ==
                    sorted(purchase_tax_ids)
                    ):
                return fc.id

        # create new Fiscal classification if not found
        if len(sale_tax_ids) == 0 and len(purchase_tax_ids) == 0:
            name = _('No taxes')
        elif len(purchase_tax_ids) == 0:
            name = _('No Purchase Taxes - Sale Taxes: ')
            for tax in at_obj.browse(sale_tax_ids):
                name += tax.description and tax.description or tax.name
                name += ' + '
            name = name[:-3]
        elif len(sale_tax_ids) == 0:
            name = _('Purchase Taxes: ')
            for tax in at_obj.browse(purchase_tax_ids):
                name += tax.description and tax.description or tax.name
                name += ' + '
            name = name[:-3]
            name += _('- No Sale Taxes')
        else:
            name = _('Purchase Taxes: ')
            for tax in at_obj.browse(purchase_tax_ids):
                name += tax.description and tax.description or tax.name
                name += ' + '
            name = name[:-3]
            name += _(' - Sale Taxes: ')
            for tax in at_obj.browse(sale_tax_ids):
                name += tax.description and tax.description or tax.name
                name += ' + '
            name = name[:-3]
        name = name[:self._MAX_LENGTH_NAME] \
            if len(name) > self._MAX_LENGTH_NAME else name
        return self.create({
            'name': name,
            'company_id': company_id,
            'sale_tax_ids': [(6, 0, sale_tax_ids)],
            'purchase_tax_ids': [(6, 0, purchase_tax_ids)]}).id

    def init(self, cr):
        """Generate Fiscal Classification for each combinations of Taxes set
        in product"""
        uid = SUPERUSER_ID
        pt_obj = self.pool['product.template']
        fc_obj = self.pool['account.product.fiscal.classification']

        # Get all Fiscal Classification (if update process)
        list_res = {}
        fc_ids = fc_obj.search(
            cr, uid, ['|', ('active', '=', False), ('active', '=', True)])
        fc_list = fc_obj.browse(cr, uid, fc_ids)
        for fc in fc_list:
            list_res[fc.id] = [
                fc.company_id and fc.company_id.id or False,
                sorted([x.id for x in fc.sale_tax_ids]),
                sorted([x.id for x in fc.purchase_tax_ids])]

        # Get all product template without Fiscal Classification defined
        pt_ids = pt_obj.search(cr, uid, [
            ('fiscal_classification_id', '=', False)])

        pt_list = pt_obj.browse(cr, uid, pt_ids)
        counter = 0
        total = len(pt_list)
        # Associate product template to existing or new Fiscal Classification
        for pt in pt_list:
            counter += 1
            args = [
                pt.company_id and pt.company_id.id or False,
                sorted([x.id for x in pt.taxes_id]),
                sorted([x.id for x in pt.supplier_taxes_id])]
            if args not in list_res.values():
                _logger.info(
                    """create new Fiscal Classification. Product templates"""
                    """ managed %s/%s""" % (counter, total))
                fc_id = self.find_or_create(cr, uid, *args)
                list_res[fc_id] = args
                # associate product template to the new Fiscal Classification
                pt_obj.write(cr, uid, [pt.id], {
                    'fiscal_classification_id': fc_id})
            else:
                # associate product template to existing Fiscal Classification
                pt_obj.write(cr, uid, [pt.id], {
                    'fiscal_classification_id': list_res.keys()[
                        list_res.values().index(args)]})
