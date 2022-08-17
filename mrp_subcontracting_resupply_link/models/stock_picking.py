# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    mrp_production_count = fields.Integer(
        compute="_compute_mrp_production_count",
    )
    mrp_subcontracting_purchase_order_count = fields.Integer(
        compute="_compute_mrp_subcontracting_purchase_order_count",
    )

    @api.depends("move_lines", "move_lines.is_subcontract", "move_lines.move_orig_ids")
    def _compute_mrp_production_count(self):
        for item in self:
            moves = item.move_lines.filtered(
                lambda x: x.is_subcontract and x.move_orig_ids
            )
            item.mrp_production_count = (
                len(moves.mapped("move_orig_ids.production_id")) if moves else 0
            )

    @api.depends("move_lines", "move_lines.rule_id", "move_lines.move_dest_ids")
    def _compute_mrp_subcontracting_purchase_order_count(self):
        for item in self:
            total = 0
            move_dests = item.move_lines.filtered(
                lambda x: x.rule_id and x.move_dest_ids
            )
            if move_dests:
                productions = move_dests.mapped(
                    "move_dest_ids.raw_material_production_id"
                )
                group = productions.picking_ids.group_id
                moves = group.stock_move_ids.move_dest_ids.filtered(
                    lambda x: x.is_subcontract and x.purchase_line_id
                )
                total = len(moves.mapped("purchase_line_id.order_id"))
            item.mrp_subcontracting_purchase_order_count = total

    def action_view_mrp_productions(self):
        self.ensure_one()
        moves = self.move_lines.filtered(lambda x: x.is_subcontract and x.move_orig_ids)
        production_ids = moves.mapped("move_orig_ids.production_id").ids
        action = {
            "res_model": "mrp.production",
            "type": "ir.actions.act_window",
        }
        if len(production_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": production_ids[0],
                }
            )
        else:
            action.update(
                {
                    "domain": [("id", "in", production_ids)],
                    "view_mode": "tree,form",
                }
            )
        return action

    def action_view_mrp_subcontracting_purchase_orders(self):
        self.ensure_one()
        move_dests = self.move_lines.filtered(lambda x: x.rule_id and x.move_dest_ids)
        productions = move_dests.mapped("move_dest_ids.raw_material_production_id")
        group = productions.picking_ids.group_id
        moves = group.stock_move_ids.move_dest_ids.filtered(
            lambda x: x.is_subcontract and x.purchase_line_id
        )
        purchase_order_ids = moves.mapped("purchase_line_id.order_id").ids
        action = {
            "res_model": "purchase.order",
            "type": "ir.actions.act_window",
        }
        if len(purchase_order_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": purchase_order_ids[0],
                }
            )
        else:
            action.update(
                {
                    "domain": [("id", "in", purchase_order_ids)],
                    "view_mode": "tree,form",
                }
            )
        return action
