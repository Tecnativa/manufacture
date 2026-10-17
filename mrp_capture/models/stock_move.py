# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _capture_is_finished_product(self):
        """The move produces the product to manufacture of its order"""
        self.ensure_one()
        return bool(
            self.production_id and self.product_id == self.production_id.product_id
        )

    @api.depends(
        "move_line_ids.quantity",
        "move_line_ids.picked",
        "production_id.capture_qty_producing",
    )
    def _compute_captured_quantity(self):
        """What is captured of the product to manufacture is what the order
        produces, as its finished lines are not picked"""
        finished = self.filtered(lambda move: move._capture_is_finished_product())
        for move in finished:
            production = move.production_id
            move.captured_quantity = production.uom_id._compute_quantity(
                production.capture_qty_producing * move.unit_factor,
                move.uom_id,
                round=False,
            )
        return super(StockMove, self - finished)._compute_captured_quantity()

    @api.depends(
        "move_line_ids.quantity",
        "move_line_ids.picked",
        "state",
        "product_uom_qty",
        "capture_forced",
        "production_id.capture_qty_producing",
    )
    def _compute_capture_state(self):
        return super()._compute_capture_state()

    def _capture_kept_lines(self):
        """Finished lines of the captures of the product to manufacture"""
        return self.move_line_ids.filtered(
            lambda ml: ml.result_package_id or ml.capture_finished_kept
        )

    def _capture_lines(
        self, quantity, uom=None, lot=None, result_package=None, merge=True, **kw
    ):
        """Captures of the product to manufacture add to what the order
        produces, whatever screen captures them"""
        if not self._capture_is_finished_product():
            return super()._capture_lines(
                quantity,
                uom=uom,
                lot=lot,
                result_package=result_package,
                merge=merge,
                **kw,
            )
        uom = uom or self.uom_id
        return self.production_id._capture_finished(
            uom._compute_quantity(quantity, self.uom_id, round=False)
            / (self.unit_factor or 1.0),
            uom=self.production_id.uom_id,
            lot=lot or None,
            result_package=result_package or None,
            merge=merge,
        )

    def action_capture_undo(self):
        finished = self.filtered(lambda move: move._capture_is_finished_product())
        for move in finished.filtered(lambda m: m.state not in ("done", "cancel")):
            production = move.production_id
            move._capture_kept_lines().unlink()
            production._capture_undo_finished(production.capture_qty_producing)
        return super(StockMove, self - finished).action_capture_undo()

    def _should_bypass_set_qty_producing(self):
        # The finished lines of the product to manufacture are kept by
        # mrp.production._capture_set_qty_producing
        if (
            self.env.context.get("capture_skip_finished_product")
            and self.production_id
            and self.product_id == self.production_id.product_id
        ):
            return True
        return super()._should_bypass_set_qty_producing()
