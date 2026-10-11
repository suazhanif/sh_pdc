# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies Pvt. Ltd.

from datetime import timedelta, date
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class Attachment(models.Model):
    """Attachment"""
    _inherit = 'ir.attachment'

    pdc_id = fields.Many2one('pdc.wizard')


class PDCWizard(models.Model):
    "PDC wiard"
    _name = "pdc.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _description = "PDC Wizard"

    # pdc only be allowed to delete in draft state
    def unlink(self):
        """Overrides unlink to prevent deletion unless in 'draft' state."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(self.env._("You can only delete draft state pdc"))

        return super().unlink()

    def action_register_check(self):
        """Opens the PDC payment wizard for the selected customer invoices."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        account_move_model = self.env[active_model].browse(active_id)

        if account_move_model.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(self.env._(
                "Only Customer invoice and vendor bills are considered!"))

        move_listt = []
        payment_amount = 0.0
        payment_type = ''
        if len(active_ids) > 0:
            account_moves = self.env[active_model].browse(active_ids)
            
            # Multi-company validation: All selected invoices must belong to the same company
            companies = account_moves.mapped('company_id')
            if len(set(companies)) != 1:
                raise UserError(self.env._('All selected invoices/bills must belong to the same company.'))

            partners = account_moves.mapped('partner_id')
            if len(set(partners)) != 1:
                raise UserError(self.env._('Partners must be same'))

            states = account_moves.mapped('state')
            if len(set(states)) != 1 or states[0] != 'posted':
                raise UserError(self.env._(
                    'Only posted invoices/bills are considered for PDC payment!!'))

            for account_move in account_moves:
                if account_move.payment_state != 'paid' and account_move.amount_residual != 0.0:
                    payment_amount = payment_amount + account_move.amount_residual
                    move_listt.append(account_move.id)
        if not move_listt:
            raise UserError(self.env._("Selected invoices are already paid!!"))

        if account_moves[0].move_type in ('in_invoice'):
            payment_type = 'send_money'

        if account_moves[0].move_type in ('out_invoice'):
            payment_type = 'receive_money'

        return {
            'name': 'PDC Payment',
            'res_model': 'pdc.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('sh_pdc.sh_pdc_wizard_form_wizard').id,
            'context': {
                'default_invoice_ids': [(6, 0, move_listt)],
                'default_partner_id': account_move_model.partner_id.id,
                'default_payment_amount': payment_amount,
                'default_payment_type': payment_type,
                'default_company_id': account_move_model.company_id.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window'
        }

    def open_attachments(self):
        """Opens a view to show attachments related to the PDC record."""
        [action] = self.env.ref('base.action_attachment').read()

        action['domain'] = [('id', 'in', self.attachment_ids.ids)]
        return action

    def open_journal_items(self):
        """Opens a view to show journal items related to the PDC record."""
        [action] = self.env.ref('account.action_account_moves_all').read()
        ids = self.env['account.move.line'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        if id_list:
            action['domain'] = [('id', 'in', id_list)]
        else:
            action['domain'] = [('id', '=', False)]
        return action

    def open_journal_entry(self):
        """Opens a view to show journal entries related to the PDC record."""
        [action] = self.env.ref(
            'sh_pdc.sh_pdc_action_move_journal_line').read()
        ids = self.env['account.move'].search([('pdc_id', '=', self.id)])
        id_list = []
        for pdc_id in ids:
            id_list.append(pdc_id.id)
        action['domain'] = [('id', 'in', id_list)]
        return action

    @api.model
    def default_get(self, fields):
        """Pre-populates the wizard with values from the selected invoice."""
        rec = super().default_get(fields)
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        # Check for selected invoices ids
        if not active_ids or active_model != 'account.move':
            return rec
        invoices = self.env['account.move'].browse(active_ids)
        if invoices:
            # Multi-company validation
            companies = invoices.mapped('company_id')
            if len(set(companies)) > 1:
                raise UserError(self.env._('All selected invoices/bills must belong to the same company.'))
            rec.update({'company_id': invoices[0].company_id.id})

        if invoices and len(invoices) == 1:
            invoice = invoices[0]
            if invoice.move_type in ('out_invoice', 'out_refund'):
                rec.update({'payment_type': 'receive_money'})
            elif invoice.move_type in ('in_invoice', 'in_refund'):
                rec.update({'payment_type': 'send_money'})

            rec.update({'partner_id': invoice.partner_id.id,
                        'payment_amount': invoice.amount_residual,
                        'invoice_id': invoice.id,
                        'due_date': invoice.invoice_date_due,
                        'memo': invoice.name})

        return rec

    name = fields.Char("Name", default='New', readonly=True, tracking=True)
    payment_type = fields.Selection([('receive_money', 'Receive Money'), (
        'send_money', 'Send Money')], string="Payment Type", default='receive_money', tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Partner", tracking=True)
    payment_amount = fields.Monetary("Payment Amount", tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string="Currency", default=lambda self: self.env.company.currency_id, tracking=True)
    reference = fields.Char("Cheque Reference", tracking=True)
    # Restricted payment journal by matching company to avoid cross-company journal postings
    journal_id = fields.Many2one('account.journal', string="Payment Journal", domain="[('type', '=', 'bank')]", required=True, tracking=True)
    
    cheque_status = fields.Selection([('draft', 'Draft'), ('deposit', 'Deposit'), (
        'paid', 'Paid')], string="Cheque Status", default='draft', tracking=True)
    payment_date = fields.Date(
        "Payment Date", default=fields.Date.today, required=True, tracking=True)
    due_date = fields.Date("Due Date", required=True, tracking=True)
    memo = fields.Char("Memo", tracking=True)
    agent = fields.Char("Agent", tracking=True)
    bank_id = fields.Many2one('res.bank', string="Bank", tracking=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pdc_attachment_rel', string='Cheque Image')
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company, tracking=True)
    invoice_id = fields.Many2one(
        'account.move', string="Invoice/Bill", tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('registered', 'Registered'), ('returned', 'Returned'),
                               ('deposited', 'Deposited'), ('bounced', 'Bounced'), ('done', 'Done'),
                               ('cancel', 'Cancelled')], string="State", default='draft', tracking=True)

    deposited_debit = fields.Many2one('account.move.line')
    deposited_credit = fields.Many2one('account.move.line')

    invoice_ids = fields.Many2many('account.move')
    account_move_ids = fields.Many2many(
        'account.move', compute="_compute_account_moves", )
    done_date = fields.Date(string="Done Date", readonly=True, tracking=True)

    @api.depends('payment_type', 'partner_id', 'company_id')
    def _compute_account_moves(self):
        """Computes open invoices of the selected partner and type, scoped to the PDC's company."""
        for rec in self:
            rec.account_move_ids = False
            if not rec.company_id:
                continue
            domain = [('partner_id', '=', rec.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0),
                      ('state', '=', 'posted'), ('company_id', '=', rec.company_id.id)]

            if rec.payment_type == 'receive_money':
                domain.extend([('move_type', '=', 'out_invoice')])
            else:
                domain.extend([('move_type', '=', 'in_invoice')])

            moves = self.env['account.move'].search(domain)
            rec.account_move_ids = moves.ids

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Automatically clears the journal if the new company doesn't match the journal's company."""
        if self.journal_id and self.journal_id.company_id and self.journal_id.company_id != self.company_id:
            self.journal_id = False

        if not self.company_id:
            return {'domain': {'journal_id': [('type', '=', 'bank')]}}
        else:
            return {'domain': {'journal_id': [('type', '=', 'bank'), '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]}}

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """Automatically updates the company to match the selected journal's company."""
        if self.journal_id and self.journal_id.company_id:
            self.company_id = self.journal_id.company_id.id

    @api.constrains('journal_id', 'company_id')
    def _check_company_journal(self):
        """Ensures that the selected journal belongs to the selected company to prevent database transaction errors."""
        for rec in self:
            if rec.journal_id and rec.journal_id.company_id and rec.journal_id.company_id != rec.company_id:
                raise ValidationError(self.env._("The selected payment journal must belong to the selected company!"))


    @api.onchange('partner_id', 'company_id')
    def _onchange_partner(self):
        if self.company_id and self.company_id.auto_fill_open_invoice:
            domain = [('partner_id', '=', self.partner_id.id), ('payment_state', '!=',
                                                                'paid'), ('amount_residual', '!=', 0.0),
                      ('state', '=', 'posted'), ('company_id', '=', self.company_id.id)]

            if self.payment_type == 'receive_money':
                domain.extend([('move_type', '=', 'out_invoice')])
            else:
                domain.extend([('move_type', '=', 'in_invoice')])
            moves = self.env['account.move'].search(domain)
            self.invoice_ids = [(6, 0, moves.ids)]

    def button_register(self):
        """Main button to register the PDC and advance its state."""
        listt = []
        if self:
            if self.invoice_id:
                listt.append(self.invoice_id.id)
            if self.invoice_ids:
                listt.extend(self.invoice_ids.ids)

            self.write({
                'invoice_ids': [(6, 0, list(set(listt)))]
            })

            if self.cheque_status == 'draft':
                self.write({'state': 'draft'})

            if self.cheque_status == 'deposit':
                self.action_register()
                self.action_deposited()
                self.write({'state': 'deposited'})

            if self.cheque_status == 'paid':
                self.action_register()
                self.action_deposited()
                self.action_done()
                self.write({'state': 'done'})

    def action_register(self):
        """Validates payment amount and moves the PDC state to 'registered'."""
        self.check_payment_amount()

        if self.invoice_ids:
            list_amount_residuals = self.invoice_ids.mapped('amount_residual')# pylint: disable=E1101
            amount = (self.currency_id.round(sum(list_amount_residuals))
                      if self.currency_id else round(sum(list_amount_residuals), 2))

            if self.payment_amount > amount and amount != 0:
                raise UserError(self.env._(
                    "Payment amount is greater than total invoice/bill amount!!!"))

        self.write({'state': 'registered'})

    def check_payment_amount(self):
        """Validates that the payment amount is greater than zero."""
        if self.payment_amount <= 0.0:
            raise UserError(self.env._("Amount must be greater than zero!"))

    def check_pdc_account(self):
        """Checks and returns the appropriate PDC suspense account, scoped to self.company_id."""
        if self.payment_type == 'receive_money':
            if not self.company_id.pdc_customer:
                raise UserError(self.env._(
                    "Please Set PDC payment account for Customer !"))
            else:
                return self.company_id.pdc_customer.id
        else:
            if not self.company_id.pdc_vendor:
                raise UserError(self.env._(
                    "Please Set PDC payment account for Supplier !"))
            else:
                return self.company_id.pdc_vendor.id

    def get_partner_account(self):
        """Returns the partner's receivable or payable account, scoped to matching company."""
        partner = self.partner_id.with_company(self.company_id)
        if self.payment_type == 'receive_money':
            account = partner.property_account_receivable_id
        else:
            account = partner.property_account_payable_id
        if not account:
            raise UserError(self.env._("Partner is missing a valid receivable or payable account."))
        return account.id

    def action_returned(self):
        """Moves the PDC state to 'returned'."""
        self.check_payment_amount()
        self.write({'state': 'returned'})

    def get_debit_move_line(self, account):
        """Helper method to prepare a dictionary for a debit journal line, explicitly set company_id."""
        if not account:
            raise UserError(self.env._("Missing debit account for PDC transaction."))
        return {
            'pdc_id': self.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'account_id': account,
            'debit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
            'company_id': self.company_id.id,
        }

    def get_credit_move_line(self, account):
        """Helper method to prepare a dictionary for a credit journal line, explicitly set company_id."""
        if not account:
            raise UserError(self.env._("Missing credit account for PDC transaction."))
        return {
            'pdc_id': self.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'account_id': account,
            'credit': self.payment_amount,
            'ref': self.memo,
            'date': self.payment_date,
            'date_maturity': self.due_date,
            'company_id': self.company_id.id,
        }

    def get_move_vals(self, debit_line, credit_line):
        """Helper method to prepare a dictionary for an account.move record, explicitly set company_id."""
        return {
            'pdc_id': self.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.commercial_partner_id.id,
            'ref': self.memo,
            'move_type': 'entry',
            'company_id': self.company_id.id,
            'line_ids': [(0, 0, debit_line),
                         (0, 0, credit_line)]
        }

    def action_deposited(self):
        "Action Deposit"
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}
        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Deposit  :' + self.memo})
            move_line_vals_credit.update({'name': 'PDC Deposit :' + self.memo})
        else:
            move_line_vals_debit.update({'name': 'PDC Deposit'})
            move_line_vals_credit.update({'name': 'PDC Deposit'})

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        self.write({
            'state': 'deposited',
        })

        move_id = move.create(move_vals)
        move_id.action_post()

        self.write({'deposited_debit': move_id.line_ids.filtered(lambda x: x.debit > 0),
                    'deposited_credit': move_id.line_ids.filtered(lambda x: x.credit > 0)})

    def action_bounced(self):
        "Action Bounced"
        move = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        partner_account = self.get_partner_account()

        # Create Journal Item
        move_line_vals_debit = {}
        move_line_vals_credit = {}

        if self.payment_type == 'receive_money':
            move_line_vals_debit = self.get_debit_move_line(partner_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(partner_account)

        if self.memo:
            move_line_vals_debit.update({'name': 'PDC Payment Bounce  :' + self.memo})
            move_line_vals_credit.update({'name': 'PDC Payment Bounce :' + self.memo})
        else:
            move_line_vals_debit.update({'name': 'PDC Payment Bounce'})
            move_line_vals_credit.update({'name': 'PDC Payment Bounce'})
        original_deposit_lines = self.deposited_debit | self.deposited_credit

        # create move and post it
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)

        bounce_move = move.create(move_vals)
        bounce_move.action_post()

        # Reconcile for partner_account
        lines_to_reconcile = (original_deposit_lines | bounce_move.line_ids).filtered(
            lambda r: r.account_id.id == partner_account
        )
        if lines_to_reconcile and len(lines_to_reconcile) > 1:
            lines_to_reconcile.reconcile()

        # Reconcile for pdc_account
        pdc_lines = (original_deposit_lines | bounce_move.line_ids).filtered(
            lambda r: r.account_id.id == pdc_account
        )
        if pdc_lines and len(pdc_lines) > 1:
            pdc_lines.reconcile()

        self.write({
            'state': 'bounced',
            'deposited_debit': False,
            'deposited_credit': False,
        })

    def get_reconcilation_domain(self):
        """Helper method to return the domain for identifying reconcilable lines."""
        return [
            ('parent_state', '=', 'posted'),
            ('account_type', 'in', ('asset_receivable', 'liability_payable')),
            ('reconciled', '=', False),
        ]

    def action_done(self):
        """Finalizes the PDC workflow, creating and reconciling entries."""
        self.ensure_one()
        move_obj = self.env['account.move']

        self.check_payment_amount()  # amount must be positive
        pdc_account = self.check_pdc_account()
        bank_account = self.journal_id._get_journal_inbound_outstanding_payment_accounts() if self.payment_type == 'receive_money' else self.journal_id._get_journal_outbound_outstanding_payment_accounts()
        bank_account = bank_account[0].id if bank_account else False

        pdc_deposit_move_lines = self.deposited_debit | self.deposited_credit

        # Reconcile invoices with deposit partner account lines (e.g. 121000)
        domain = self.get_reconcilation_domain()
        (self.invoice_ids.line_ids | pdc_deposit_move_lines).filtered_domain(domain).reconcile()

        # Create Final Journal Entry (Done)
        is_receive_money = self.payment_type == 'receive_money'
        if is_receive_money:
            move_line_vals_debit = self.get_debit_move_line(bank_account)
            move_line_vals_credit = self.get_credit_move_line(pdc_account)
        else:
            move_line_vals_debit = self.get_debit_move_line(pdc_account)
            move_line_vals_credit = self.get_credit_move_line(bank_account)

        if self.memo:
            move_line_vals_debit.update(
                {'name': 'PDC Payment :' + self.memo, 'partner_id': self.partner_id.commercial_partner_id.id})
            move_line_vals_credit.update(
                {'name': 'PDC Payment :' + self.memo, 'partner_id': self.partner_id.commercial_partner_id.id})
        else:
            move_line_vals_debit.update(
                {'name': 'PDC Payment', 'partner_id': self.partner_id.commercial_partner_id.id})
            move_line_vals_credit.update(
                {'name': 'PDC Payment', 'partner_id': self.partner_id.commercial_partner_id.id})

        # create and post final move
        move_vals = self.get_move_vals(
            move_line_vals_debit, move_line_vals_credit)
        done_move = move_obj.create(move_vals)
        done_move.action_post()

        # Reconcile Done entry with deposit entry for the PDC suspense account (e.g. 100011)
        (done_move.line_ids | pdc_deposit_move_lines).filtered(lambda line: line.account_id.id == pdc_account).reconcile()

        self.write({
            'state': 'done',
            'done_date': date.today(),
        })

    def action_cancel(self):
        """Cancels the PDC record based on the company's policy."""
        self.action_delete_related_moves()
        if self.company_id.pdc_operation_type == 'cancel':
            self.write({'state': 'cancel'})

        elif self.company_id.pdc_operation_type == 'cancel_draft':
            self.write({'state': 'draft'})

        elif self.company_id.pdc_operation_type == 'cancel_delete':
            self.write({'state': 'draft'})
            self.unlink()
            return {'type': 'ir.actions.act_window_close'}

    def action_pdc_cancel(self):
        """Sets the PDC state to 'cancel' and reverses related entries."""
        self.action_delete_related_moves()
        self.write({'state': 'cancel'})

    def action_pdc_cancel_draft(self):
        """Sets the PDC state to 'draft' and reverses related entries."""
        self.action_delete_related_moves()
        self.write({'state': 'draft'})

    def action_pdc_cancel_delete(self):
        """Deletes the PDC record and reverses related entries."""
        self.action_delete_related_moves()
        self.write({'state': 'draft'})
        self.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        """Overrides create to assign a sequence number."""
        for vals in vals_list:
            if vals.get('payment_type') == 'receive_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.customer')
            elif vals.get('payment_type') == 'send_money':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pdc.payment.vendor')

        res = super().create(vals_list)
        res.attachment_ids.write({
            'res_id': res.id
        })
        return res

    # ==============================
    #    CRON SCHEDULER CUSTOMER
    # ==============================
    @api.model
    def notify_customer_due_date(self):
        """Scheduled action to send notifications for PDCs nearing due date."""
        companies = self.env['res.company'].search([('is_cust_due_notify', '=', True)])
        for company in companies:
            emails = []
            notify_day_1 = company.notify_on_1
            notify_day_2 = company.notify_on_2
            notify_day_3 = company.notify_on_3
            notify_day_4 = company.notify_on_4
            notify_day_5 = company.notify_on_5
            notify_date_1 = False
            notify_date_2 = False
            notify_date_3 = False
            notify_date_4 = False
            notify_date_5 = False
            if notify_day_1:
                notify_date_1 = fields.Date.today() + timedelta(days=int(notify_day_1) * -1)
            if notify_day_2:
                notify_date_2 = fields.Date.today() + timedelta(days=int(notify_day_2) * -1)
            if notify_day_3:
                notify_date_3 = fields.Date.today() + timedelta(days=int(notify_day_3) * -1)
            if notify_day_4:
                notify_date_4 = fields.Date.today() + timedelta(days=int(notify_day_4) * -1)
            if notify_day_5:
                notify_date_5 = fields.Date.today() + timedelta(days=int(notify_day_5) * -1)

            records = self.search([
                ('payment_type', '=', 'receive_money'),
                ('company_id', '=', company.id),
                ('state', 'not in', ['done', 'cancel'])
            ])
            for user in company.sh_user_ids:
                if user.partner_id and user.partner_id.email:
                    emails.append(user.partner_id.email)
            
            if not emails:
                continue

            email_values = {
                'email_to': ','.join(emails),
            }
            view = self.env.ref(
                "sh_pdc.sh_pdc_payment_form_view", raise_if_not_found=False).sudo()
            view_id = view.id if view else 0
            for record in records:
                if (record.due_date == notify_date_1
                    or record.due_date == notify_date_2
                    or record.due_date == notify_date_3
                    or record.due_date == notify_date_4
                        or record.due_date == notify_date_5):

                    if company.is_notify_to_customer:
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_customer_notification_1', raise_if_not_found=False)
                        if template_download_id:
                            _ = record.env['mail.template'].browse(
                                template_download_id.id
                            ).send_mail(record.id, email_layout_xmlid='mail.mail_notification_light', force_send=True)
                    if company.is_notify_to_user and company.sh_user_ids:
                        url = ''
                        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                        url = base_url + "/web#id=" + \
                            str(record.id) + \
                            "&&model=pdc.wizard&view_type=form&view_id=" + \
                            str(view_id)
                        ctx = {
                            "customer_url": url,
                        }
                        template_download_id = self.env.ref(
                            'sh_pdc.sh_pdc_company_to_int_user_notification_1', raise_if_not_found=False)
                        if template_download_id:
                            self.env['mail.template'].sudo().browse(template_download_id.id).with_context(
                                **ctx).send_mail(
                                record.id, email_values=email_values, email_layout_xmlid='mail.mail_notification_light',
                                force_send=True)

    def action_set_draft(self):
        """Resets the PDC record to the 'draft' state."""
        self.sudo().write({
            'state': 'draft',
        })

    def action_delete_related_moves(self):
        """Finds and deletes all journal entries related to this PDC."""
        for model in self:
            move_ids = self.env['account.move'].search(
                [('pdc_id', '=', model.id)])
            for move in move_ids:
                move.button_draft()
                lines = self.env['account.move.line'].search(
                    [('move_id', '=', move.id)])
                lines.unlink()

            model.sudo().write({
                'done_date': False
            })

            for move in move_ids:
                self.env.cr.execute(
                    "DELETE FROM account_move WHERE id = %s", (move.id,)
                )

    def action_state_register(self):
        """Server action for mass-registering PDCs."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'draft':
                    for active_model in active_models:
                        active_model.action_register()
                else:
                    raise UserError(self.env._(
                        "Only Draft state PDC check can switch to Register state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))

    def action_state_return(self):
        """Server action for mass-returning PDCs."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'registered':
                    for active_model in active_models:
                        active_model.action_returned()
                else:
                    raise UserError(self.env._(
                        "Only Register state PDC check can switch to return state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))

    def action_state_deposit(self):
        """Server action for mass-depositing PDCs."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_deposited()
                else:
                    raise UserError(self.env._(
                        "Only Register,Return and Bounce state PDC check can switch to Deposit state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))

    def action_state_bounce(self):
        """Server action for mass-bouncing PDCs."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_bounced()
                else:
                    raise UserError(self.env._(
                        "Only Deposit state PDC check can switch to Bounce state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))

    def action_state_done(self):
        """Server action for mass-marking PDCs as done."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] == 'deposited':
                    for active_model in active_models:
                        active_model.action_done()
                else:
                    raise UserError(self.env._(
                        "Only Deposit state PDC check can switch to Done state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))

    def action_state_cancel(self):
        """Server action for mass-cancelling PDCs."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if len(active_ids) > 0:
            active_models = self.env[active_model].browse(active_ids)
            states = active_models.mapped('state')

            if len(set(states)) == 1:
                if states[0] in ['registered', 'returned', 'bounced']:
                    for active_model in active_models:
                        active_model.action_cancel()
                else:
                    raise UserError(self.env._(
                        "Only Register,Return and Bounce state PDC check can switch to Cancel state!!"))
            else:
                raise UserError(self.env._(
                    "States must be same!!"))
