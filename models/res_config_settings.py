# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies Pvt. Ltd.
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pdc_customer = fields.Many2one('account.account', string="PDC Account for customer",
                                   related='company_id.pdc_customer', readonly=False)
    pdc_vendor = fields.Many2one('account.account', string="PDC Account for Vendor",
                                 related='company_id.pdc_vendor', readonly=False)
    auto_fill_open_invoice = fields.Boolean(string="Auto Fill open Invoice in PDC on Customer Selection",
                                            related="company_id.auto_fill_open_invoice", readonly=False)
    pdc_operation_type = fields.Selection(
        related="company_id.pdc_operation_type", readonly=False)


    is_cust_due_notify = fields.Boolean('Customer Due Notification',
                                        related='company_id.is_cust_due_notify', readonly=False)
    is_notify_to_customer = fields.Boolean('Notify to Customer',
                                           related='company_id.is_notify_to_customer', readonly=False)
    is_notify_to_user = fields.Boolean('Notify to Internal User',
                                       related='company_id.is_notify_to_user', readonly=False)
    sh_user_ids = fields.Many2many('res.users', string='Responsible User',
                                   related='company_id.sh_user_ids', readonly=False)
    notify_on_1 = fields.Char('Notify On 1',
                              related='company_id.notify_on_1', readonly=False)
    notify_on_2 = fields.Char('Notify On 2',
                              related='company_id.notify_on_2', readonly=False)
    notify_on_3 = fields.Char('Notify On 3',
                              related='company_id.notify_on_3', readonly=False)
    notify_on_4 = fields.Char('Notify On 4',
                              related='company_id.notify_on_4', readonly=False)
    notify_on_5 = fields.Char('Notify On 5',
                              related='company_id.notify_on_5', readonly=False)
