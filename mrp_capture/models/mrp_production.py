# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import Command, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _name = "mrp.production"
    _inherit = ("mrp.production", "stock.capture.document")

    capture_qty_producing = fields.Float(
        string="Captured Quantity",
        digits="Product Unit",
        copy=False,
        help="Quantity of the product to manufacture captured by reading or "
        "weighing it, which becomes the quantity to produce.",
    )

    def _capture_check_state(self):
        self.ensure_one()
        if self.state in ("draft", "done", "cancel"):
            raise UserError(
                self.env._(
                    "Quantities can only be captured on confirmed manufacturing orders."
                )
            )

    def _capture_product(
        self,
        product,
        quantity,
        uom=None,
        lot=None,
        location=None,
        package=None,
        owner=None,
        result_package=None,
    ):
        """Capture a quantity of a product on the manufacturing order.

        The product to manufacture adds to the quantity to produce, a byproduct
        is captured on its moves and any other product is consumed as a
        component.

        :return: the move lines holding the captured quantity
        """
        self.ensure_one()
        if product == self.product_id:
            return self._capture_finished(
                quantity, uom=uom, lot=lot, result_package=result_package
            )
        byproduct_moves = self.move_byproduct_ids.filtered(
            lambda move: (
                move.product_id == product and move.state not in ("done", "cancel")
            )
        )
        if byproduct_moves:
            self._capture_check_state()
            return byproduct_moves._capture_spread(
                quantity, uom=uom, lot=lot, result_package=result_package
            )
        return self._capture_component(
            product,
            quantity,
            uom=uom,
            lot=lot,
            location=location,
            package=package,
            owner=owner,
            result_package=result_package,
        )

    def _capture_component(self, product, quantity, uom=None, **characteristics):
        """Consume a captured quantity of a component.

        A component without moves in the order gets a new one, as when it is
        added to the order by hand.

        :return: the picked move lines holding the captured quantity
        """
        self._capture_check_state()
        uom = uom or product.uom_id
        moves = self.move_raw_ids.filtered(
            lambda move: (
                move.product_id == product and move.state not in ("done", "cancel")
            )
        )
        if not moves:
            moves = self.env["stock.move"].create(
                self._get_move_raw_values(product, 0.0, uom)
            )
            moves._action_confirm()
        return moves._capture_spread(quantity, uom=uom, **characteristics)

    def _capture_finished_move(self):
        self.ensure_one()
        return self.move_finished_ids.filtered(
            lambda move: (
                move.product_id == self.product_id
                and move.state not in ("done", "cancel")
            )
        )[:1]

    def _capture_finished(
        self, quantity, uom=None, lot=None, result_package=None, merge=True
    ):
        """Capture a quantity of the product to manufacture.

        It adds to the quantity to produce, as Odoo's barcode application does,
        instead of picking the finished move, which Odoo would take as already
        produced. With a destination package, the quantity gets its own
        finished line in that package, and without merging, a line of its own,
        e.g. one per weighing to label it.

        :return: the finished move line holding the captured quantity
        """
        self._capture_check_state()
        if lot and lot not in self.lot_producing_ids:
            if self.product_tracking == "lot" and self.lot_producing_ids:
                raise UserError(
                    self.env._("A manufacturing order produces a single lot.")
                )
            self.lot_producing_ids = [Command.link(lot.id)]
        result_package = self.picking_type_id._capture_result_package(
            result_package, self._capture_finished_move().location_dest_id
        )
        quantity = (uom or self.uom_id)._compute_quantity(
            quantity, self.uom_id, round=False
        )
        # The quantity to produce is what has been captured, whatever Odoo set
        # before, e.g. the order quantity when a work order is started
        self.capture_qty_producing += quantity
        self.qty_producing = self.capture_qty_producing
        self._capture_set_qty_producing()
        move = self._capture_finished_move()
        rest_line = move.move_line_ids - move._capture_kept_lines()
        if not result_package and merge:
            return rest_line
        line_quantity = move.uom_id._compute_quantity(
            quantity * move.unit_factor, rest_line.uom_id, round=False
        )
        target = result_package and move.move_line_ids.filtered(
            lambda ml: ml.result_package_id == result_package
        )
        if target:
            target_quantity = rest_line.uom_id._compute_quantity(
                line_quantity, target.uom_id, round=False
            )
            rest_line._capture_finished_give(line_quantity)
            target.quantity += target_quantity
            return target
        package_id = result_package.id if result_package else False
        if rest_line.uom_id.compare(line_quantity, rest_line.quantity) < 0:
            rest_line._split(line_quantity, package_id)
        elif result_package:
            rest_line.result_package_id = result_package
        rest_line.capture_finished_kept = True
        return rest_line

    def _capture_undo_finished(
        self, quantity, uom=None, result_package=None, line=None
    ):
        """Undo a quantity captured of the product to manufacture, taking it out
        of the given finished line or of the one in the destination package"""
        self._capture_check_state()
        quantity = min(
            (uom or self.uom_id)._compute_quantity(quantity, self.uom_id, round=False),
            self.capture_qty_producing,
        )
        move = self._capture_finished_move()
        if not line and result_package:
            line = move.move_line_ids.filtered(
                lambda ml: ml.result_package_id == result_package
            )
        if line:
            line_quantity = move.uom_id._compute_quantity(
                quantity * move.unit_factor, line.uom_id, round=False
            )
            if line.uom_id.compare(line_quantity, line.quantity) < 0:
                line.quantity -= line_quantity
            else:
                line.unlink()
        self.capture_qty_producing -= quantity
        self.qty_producing = self.capture_qty_producing
        self._capture_set_qty_producing()

    def _capture_set_qty_producing(self):
        """Update the order to its quantity to produce, keeping the finished
        lines of the captures.

        Odoo would rewrite the finished lines of the product to manufacture,
        which can shrink or drop the ones in packages depending on their order.
        Here the lines of the captures (in packages or kept on their own) keep
        their quantities and a single other line holds the rest.
        """
        self.ensure_one()
        self.with_context(capture_skip_finished_product=True)._set_qty_producing(False)
        move = self._capture_finished_move()
        if not move:
            return
        quantity = self.qty_producing - self.qty_produced
        if self.uom_id.is_zero(quantity):
            # As Odoo, show the quantity to produce until something is captured
            quantity = self.product_qty - self.qty_produced
        quantity = move.uom_id.round(quantity * move.unit_factor)
        kept_lines = move._capture_kept_lines()
        rest = quantity - sum(
            line.uom_id._compute_quantity(line.quantity, move.uom_id, round=False)
            for line in kept_lines
        )
        rest_lines = move.move_line_ids - kept_lines
        if move.uom_id.compare(rest, 0) <= 0:
            rest_lines.unlink()
        elif rest_lines:
            rest_lines[1:].unlink()
            rest_lines[0].quantity = move.uom_id._compute_quantity(
                rest, rest_lines[0].uom_id, round=False
            )
        else:
            self.env["stock.move.line"].create(
                move._prepare_move_line_vals(
                    quantity=move.uom_id._compute_quantity(
                        rest, move.product_id.uom_id, round=False
                    )
                )
            )
        if self.product_tracking == "lot" and self.lot_producing_ids:
            # Lines created before the lot to produce was known
            move.move_line_ids.filtered(
                lambda ml: not ml.lot_id
            ).lot_id = self.lot_producing_ids[:1]

    def _capture_drop_unpicked_lines(self, moves):
        """Drop the lines left unpicked on the moves with captured quantities.

        Odoo drops them when it validates the moves, but before that it counts
        them in the consumption warning and marking the byproducts as produced
        picks them.
        """
        moves.filtered(
            lambda move: move.picked and move.state not in ("done", "cancel")
        ).move_line_ids.filtered(lambda ml: not ml.picked).unlink()

    def _mark_byproducts_as_produced(self):
        for production in self:
            production._capture_drop_unpicked_lines(production.move_byproduct_ids)
        return super()._mark_byproducts_as_produced()

    def pre_button_mark_done(self):
        for production in self:
            if not production.uom_id.is_zero(
                production.capture_qty_producing
            ) and production.uom_id.compare(
                production.qty_producing, production.capture_qty_producing
            ):
                # What was captured is produced, whatever was set by hand
                production.qty_producing = production.capture_qty_producing
                production._capture_set_qty_producing()
            production._capture_drop_unpicked_lines(production.move_raw_ids)
        return super().pre_button_mark_done()

    # Capture document: components, product to manufacture and byproducts

    def _capture_profile(self):
        return self.picking_type_id._capture_profile()

    def _capture_moves(self):
        return self.move_raw_ids | self.move_finished_ids

    def _capture_source_locations(self):
        return self.location_src_id

    def _capture_dest_locations(self):
        return self.location_dest_id

    def _capture_info(self):
        info = super()._capture_info()
        info["company_id"] = self.company_id
        return info

    def _capture_is_produced(self, product):
        return (
            product == self.product_id or product in self.move_byproduct_ids.product_id
        )

    def _capture_candidate_moves(self, session):
        """Components are captured whether they are reserved or not"""
        return self._capture_moves().filtered(
            lambda move: (
                move.product_id == session.product_id
                and move.state not in ("draft", "done", "cancel")
            )
        )

    def _capture_check(self, session):
        if self._capture_is_produced(session.product_id):
            # What is produced is neither taken from the stock nor limited
            return True
        return super()._capture_check(session)

    def _capture_can_create_lot(self, product):
        return (
            self._capture_is_produced(product) and self.picking_type_id.use_create_lots
        )

    def _capture_apply(self, session):
        values = session._capture_characteristics()
        return self._capture_product(
            session.product_id,
            values["quantity"],
            uom=values["uom"],
            lot=values["lot"],
            location=values["location"],
            package=values["package"],
            owner=values["owner"],
            result_package=values["result_package"],
        )

    def _capture_can_validate(self):
        return self.state in ("confirmed", "progress", "to_close")

    def _capture_validate(self, session):
        result = self.with_context(capture_session_id=session.id).button_mark_done()
        if result is True:
            return session._capture_after_validate()
        return result

    def _capture_done_action(self, session):
        return self.get_record_default_action()
