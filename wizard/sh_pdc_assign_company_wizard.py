# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies Pvt. Ltd.

from odoo import api, fields, models
from odoo.exceptions import UserError


class ShPdcAssignCompanyWizard(models.TransientModel):
    _name = 'sh.pdc.assign.company.wizard'
    _description = 'Assign Company to PDC'

    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)

    def action_assign_company(self):
        """Mass assigns the selected company to the active PDC records."""
        active_ids = self.env.context.get('active_ids')
        active_model = self.env.context.get('active_model')

        if not active_ids or active_model != 'pdc.wizard':
            raise UserError(self.env._("No active Post Dated Cheques found to update."))

        pdc_records = self.env['pdc.wizard'].browse(active_ids)
        
        # Update the company_id for all selected PDCs
        pdc_records.write({
            'company_id': self.company_id.id
        })

        return {'type': 'ir.actions.act_window_close'}
