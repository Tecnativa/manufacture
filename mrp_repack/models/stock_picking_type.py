# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    repack = fields.Boolean(
        string="Repacking",
        help="The manufacturing orders of this type repack a product: they "
        "consume the product they produce, so the time spent in their operations "
        "adds to its cost.",
    )
    repack_workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Repacking Work Center",
        check_company=True,
        help="Work center of the operation added to the repacking orders.",
    )
