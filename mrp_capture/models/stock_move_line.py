# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    capture_finished_kept = fields.Boolean(
        copy=False,
        help="Finished line of a capture of the product to manufacture, kept "
        "with its quantity when the quantity to produce changes",
    )

    def _capture_finished_give(self, quantity):
        """Take a quantity, in the unit of the line, out of this line of the
        rest of the product to manufacture"""
        if self.uom_id.compare(quantity, self.quantity) < 0:
            self.quantity -= quantity
        else:
            self.unlink()

    def _capture_finished_quantity(self):
        """Quantity captured on this finished line of the product to
        manufacture, in the unit of the line: a line of a capture holds what
        was captured into it, the other line the rest"""
        self.ensure_one()
        move = self.move_id
        if self.result_package_id or self.capture_finished_kept:
            return self.quantity
        production = move.production_id
        total = production.uom_id._compute_quantity(
            production.capture_qty_producing * move.unit_factor,
            self.uom_id,
            round=False,
        )
        packed = sum(
            line.uom_id._compute_quantity(line.quantity, self.uom_id, round=False)
            for line in move._capture_kept_lines()
        )
        return max(total - packed, 0.0)

    def _capture_set_quantity(self, quantity):
        """Set what is captured on a finished line of the product to
        manufacture: the difference is added to or taken from what the order
        produces"""
        self.ensure_one()
        move = self.move_id
        if not move._capture_is_finished_product():
            return super()._capture_set_quantity(quantity)
        production = move.production_id
        current = self._capture_finished_quantity()
        if self.uom_id.compare(quantity, current) == 0:
            return self
        difference = self.uom_id._compute_quantity(
            abs(quantity - current), move.uom_id, round=False
        ) / (move.unit_factor or 1.0)
        kept = self.result_package_id or self.capture_finished_kept
        if self.uom_id.compare(quantity, current) < 0:
            production._capture_undo_finished(
                difference, uom=production.uom_id, line=self if kept else None
            )
            return self.exists()
        if not kept:
            return production._capture_finished(
                difference, uom=production.uom_id, lot=self.lot_id or None
            )
        # More captured on the line of a capture
        production.capture_qty_producing += difference
        production.qty_producing = production.capture_qty_producing
        self.quantity += production.uom_id._compute_quantity(
            difference * move.unit_factor, self.uom_id, round=False
        )
        production._capture_set_qty_producing()
        return self
