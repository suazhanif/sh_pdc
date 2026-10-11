# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies Pvt. Ltd.
from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.move"

    is_boolean = fields.Boolean(compute="compute_is_boolean")

    def compute_is_boolean(self):
        for rec in self:
            rec.is_boolean = False
            if rec.pdc_payment_ids.filtered(lambda x: x.state in ['registered', 'deposited']):
                rec.is_boolean = True

    def open_pdc_payment(self):
        [action] = self.env.ref('sh_pdc.sh_pdc_payment_menu_action').read()
        action['domain'] = [('id', 'in', self.pdc_payment_ids.ids)]
        return action

    def _compute_pdc_payment(self):
        for rec in self:
            rec.pdc_payment_count = len(self.pdc_payment_ids)

    pdc_id = fields.Many2one('pdc.wizard')
    pdc_payment_ids = fields.Many2many(
        'pdc.wizard', compute='_compute_pdc_payment_invoice',search='_search_pdc_payment_ids',)
    pdc_payment_count = fields.Integer(
        "Pdc payment count", compute='_compute_pdc_payment')
    total_pdc_payment = fields.Monetary("Total ", compute='_compute_total_pdc')
    total_pdc_pending = fields.Monetary(
        "Total Pending", compute='_compute_total_pdc')
    total_pdc_cancel = fields.Monetary(
        "Total Cancel", compute='_compute_total_pdc')
    total_pdc_received = fields.Monetary(
        "Total Received", compute='_compute_total_pdc')
    sh_pdc_status = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'),
                              ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'), ('cancel', 'Cancelled')], string="PDC Status",compute='_compute_latest_pdc_payment_status',store=True)

    @api.depends('pdc_payment_ids.state')
    def _compute_latest_pdc_payment_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state


    @api.depends('pdc_payment_ids.state')
    def _compute_total_pdc(self):
        for rec in self:
            rec.total_pdc_payment = 0.0
            rec.total_pdc_pending = 0.0
            rec.total_pdc_cancel = 0.0
            rec.total_pdc_received = 0.0
            if rec.pdc_payment_ids:
                for pdc_payment in rec.pdc_payment_ids:
                    if pdc_payment.state in ('done'):
                        rec.total_pdc_received += pdc_payment.payment_amount
                    elif pdc_payment.state in ('cancel'):
                        rec.total_pdc_cancel += pdc_payment.payment_amount
                    else:
                        rec.total_pdc_pending += pdc_payment.payment_amount
            rec.total_pdc_payment = rec.total_pdc_pending + \
                rec.total_pdc_received + rec.total_pdc_cancel

    def _compute_pdc_payment_invoice(self):
        self.pdc_payment_ids = False
        for move in self:
            pdcs = self.env["pdc.wizard"].search([
                '|', ('invoice_id', '=', move.id), ('invoice_ids.id', '=', move.id)
            ])
            if pdcs:
                move.pdc_payment_ids = [(6, 0, pdcs.ids)]
                
                
    def _search_pdc_payment_ids(self, operator, value):
        pdcs = self.env['pdc.wizard'].search([('id', operator, value)])
        if pdcs:
            move_ids = pdcs.mapped('invoice_ids.id') + pdcs.mapped('invoice_id.id')
            return [('id', 'in', move_ids)]
        return [('id', '=', False)]

    def action_update_latest_pdc_status(self):
        for rec in self:
            rec.sh_pdc_status = False
            if rec.pdc_payment_ids:
                rec.sh_pdc_status = rec.pdc_payment_ids[-1].state

    def js_assign_outstanding_line(self, line_id):
        res = super().js_assign_outstanding_line(line_id)
        for invoice in self:
            line = self.env['account.move.line'].browse(line_id)
            payment_move = line.move_id
            pdcs = self.env['pdc.wizard'].search([('id', '=', payment_move.pdc_id.id)])
            if not pdcs:
                pdcs = self.env['pdc.wizard'].search([('deposited_debit', '=', line.id)])
            if not pdcs:
                pdcs = self.env['pdc.wizard'].search([('deposited_credit', '=', line.id)])
            
            if pdcs:
                pdcs.write({'invoice_ids': [(4, invoice.id)]})
                invoice._compute_latest_pdc_payment_status()

        return res