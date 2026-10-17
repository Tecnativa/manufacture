# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import Command, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_confirm(self):
        repacks = self.filtered(
            lambda production: (
                production.state == "draft" and production.picking_type_id.repack
            )
        )
        repacks._repack_prepare()
        res = super().action_confirm()
        repacks._repack_reserve_lot()
        return res

    def _repack_prepare(self):
        """Complete the repacking orders before confirming them.

        A repacking order consumes the product it produces, and its operation
        is the time spent repacking. Its consumption must be valued before its
        production: Odoo replays the moves done at the same time by id to
        compute the average cost, and the production valued first would spread
        the cost of the operation over the stock both before and after the
        repacking.
        """
        for production in self:
            product = production.product_id
            raw_moves = production.move_raw_ids.filtered(
                lambda move, product=product: move.product_id == product
            )
            if not raw_moves:
                production.move_raw_ids = [
                    Command.create(
                        production._get_move_raw_values(
                            product, production.product_qty, production.uom_id
                        )
                    )
                ]
                raw_moves = production.move_raw_ids.filtered(
                    lambda move, product=product: move.product_id == product
                )
            workcenter = production.picking_type_id.repack_workcenter_id
            if workcenter and not production.workorder_ids:
                production.workorder_ids = [
                    Command.create(
                        {
                            "name": production.picking_type_id.name,
                            "workcenter_id": workcenter.id,
                        }
                    )
                ]
            # Odoo recreates the finished moves of draft orders on most changes
            finished_moves = production.move_finished_ids.filtered(
                lambda move, product=product: move.product_id == product
            )
            if finished_moves and min(finished_moves.ids) < max(raw_moves.ids):
                finished_values = [
                    values
                    for values in production._get_moves_finished_values()
                    if values["product_id"] == product.id
                ]
                production.move_finished_ids = [
                    Command.delete(move.id) for move in finished_moves
                ] + [Command.create(values) for values in finished_values]

    def _repack_reserve_lot(self):
        """Reserve the product to repack from the lot to produce, which is kept"""
        for production in self:
            lot = production.lot_producing_ids[:1]
            if production.product_tracking != "lot" or not lot:
                continue
            raw_moves = production.move_raw_ids.filtered(
                lambda move, production=production, lot=lot: (
                    move.product_id == production.product_id
                    and move.state not in ("done", "cancel")
                    and move.move_line_ids.lot_id != lot
                )
            )
            for move in raw_moves:
                move._do_unreserve()
                move._update_reserved_quantity(
                    move.product_qty, move.location_id, lot_id=lot, strict=False
                )
            raw_moves._recompute_state()
