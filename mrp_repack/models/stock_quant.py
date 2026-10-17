# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import Command, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _get_repack_picking_type(self):
        self.ensure_one()
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "mrp_operation"),
                ("repack", "=", True),
                ("warehouse_id", "=", self.warehouse_id.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not picking_type:
            raise UserError(
                self.env._(
                    "There is no repacking operation type in the warehouse %s.",
                    self.warehouse_id.display_name,
                )
            )
        return picking_type

    def action_repack(self):
        """Create a confirmed repacking order for each of these quants"""
        productions = self.env["mrp.production"]
        for quant in self:
            productions |= productions.create(
                {
                    "product_id": quant.product_id.id,
                    "product_qty": quant.quantity,
                    "uom_id": quant.product_id.uom_id.id,
                    "picking_type_id": quant._get_repack_picking_type().id,
                    "location_src_id": quant.location_id.id,
                    "lot_producing_ids": [Command.set(quant.lot_id.ids)],
                }
            )
        productions.action_confirm()
        action = self.env["ir.actions.actions"]._for_xml_id("mrp.mrp_production_action")
        action["domain"] = [("id", "in", productions.ids)]
        if len(productions) == 1:
            action.update(
                {
                    "views": [(False, "form")],
                    "view_mode": "form",
                    "res_id": productions.id,
                }
            )
        return action
