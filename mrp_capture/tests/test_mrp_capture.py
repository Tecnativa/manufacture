# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMrpCapture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.stock_location = cls.env.ref("stock.warehouse0").lot_stock_id
        cls.Quant = cls.env["stock.quant"]
        Product = cls.env["product.product"]
        cls.finished = Product.create({"name": "Fillets", "is_storable": True})
        cls.component_a = Product.create({"name": "Fish", "is_storable": True})
        cls.component_b = Product.create({"name": "Tray", "is_storable": True})
        cls.component_c = Product.create({"name": "Ice", "is_storable": True})
        cls.byproduct = Product.create({"name": "Trimmings", "is_storable": True})
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    Command.create(
                        {"product_id": cls.component_a.id, "product_qty": 2.0}
                    ),
                    Command.create(
                        {"product_id": cls.component_b.id, "product_qty": 1.0}
                    ),
                ],
                "byproduct_ids": [
                    Command.create({"product_id": cls.byproduct.id, "product_qty": 1.0})
                ],
            }
        )
        for product in cls.component_a | cls.component_b | cls.component_c:
            cls.Quant._update_available_quantity(product, cls.stock_location, 100.0)
        Package = cls.env["stock.package"]
        cls.package_1 = Package.create({"name": "MRP-CAPTURE-P1"})
        cls.package_2 = Package.create({"name": "MRP-CAPTURE-P2"})

    def _create_production(self, quantity=5.0):
        production_form = Form(self.env["mrp.production"])
        production_form.product_id = self.finished
        production_form.bom_id = self.bom
        production_form.product_qty = quantity
        production = production_form.save()
        production.action_confirm()
        return production

    def _move(self, moves, product):
        return moves.filtered(lambda move: move.product_id == product)

    def _mark_done(self, production):
        action = production.button_mark_done()
        while isinstance(action, dict) and action.get("res_model"):
            wizard = Form(
                self.env[action["res_model"]].with_context(**action["context"])
            ).save()
            if action["res_model"] == "mrp.consumption.warning":
                action = wizard.action_confirm()
            else:
                self.assertEqual(action["res_model"], "mrp.production.backorder")
                action = wizard.action_close_mo()
        self.assertEqual(production.state, "done")

    def _reserved(self, product):
        return sum(
            self.Quant._gather(product, self.stock_location).mapped("reserved_quantity")
        )

    def test_capture_finished_is_the_quantity_to_produce(self):
        production = self._create_production()
        finished_move = self._move(production.move_finished_ids, self.finished)
        production._capture_product(self.finished, 2.0)
        production._capture_product(self.finished, 1.5)
        self.assertEqual(production.qty_producing, 3.5)
        # A picked finished move would be taken as already produced
        self.assertFalse(finished_move.picked)
        self.assertEqual(production.qty_produced, 0.0)
        self.assertEqual(finished_move.quantity, 3.5)
        self.assertEqual(len(finished_move.move_line_ids), 1)
        self.assertEqual(
            self._move(production.move_raw_ids, self.component_b).quantity, 3.5
        )
        self._mark_done(production)
        self.assertEqual(self.finished.qty_available, 3.5)
        self.assertEqual(self.component_a.qty_available, 93.0)

    def test_capture_finished_in_packages(self):
        production = self._create_production()
        finished_move = self._move(production.move_finished_ids, self.finished)
        production._capture_product(self.finished, 2.0, result_package=self.package_1)
        production._capture_product(self.finished, 3.0, result_package=self.package_2)
        production._capture_product(self.finished, 1.0, result_package=self.package_1)
        self.assertEqual(production.qty_producing, 6.0)
        self.assertEqual(
            {(ml.result_package_id, ml.quantity) for ml in finished_move.move_line_ids},
            {(self.package_1, 3.0), (self.package_2, 3.0)},
        )
        self._mark_done(production)
        quants = self.Quant._gather(self.finished, self.stock_location)
        self.assertEqual(
            {(quant.package_id, quant.quantity) for quant in quants},
            {(self.package_1, 3.0), (self.package_2, 3.0)},
        )

    def test_capture_finished_without_package_after_packages(self):
        production = self._create_production()
        finished_move = self._move(production.move_finished_ids, self.finished)
        production._capture_product(self.finished, 2.0, result_package=self.package_1)
        production._capture_product(self.finished, 1.0)
        production._capture_product(self.finished, 1.0)
        self.assertEqual(
            {(ml.result_package_id, ml.quantity) for ml in finished_move.move_line_ids},
            {(self.package_1, 2.0), (self.env["stock.package"], 2.0)},
        )
        self._mark_done(production)
        self.assertEqual(self.finished.qty_available, 4.0)

    def test_capture_finished_after_work_order_start(self):
        workcenter = self.env["mrp.workcenter"].create({"name": "Weighing"})
        production = self._create_production()
        production.workorder_ids = [
            Command.create(
                {
                    "name": "Weigh",
                    "workcenter_id": workcenter.id,
                }
            )
        ]
        production.workorder_ids.button_start()
        # Odoo sets the order quantity as the quantity to produce
        self.assertEqual(production.qty_producing, 5.0)
        production._capture_product(self.finished, 2.0)
        self.assertEqual(production.qty_producing, 2.0)
        production._capture_product(self.finished, 1.5)
        self.assertEqual(production.qty_producing, 3.5)

    def test_capture_finished_lot_in_packages(self):
        self.finished.tracking = "lot"
        lot = self.env["stock.lot"].create(
            {"name": "MRP-CAPTURE-LOT3", "product_id": self.finished.id}
        )
        production = self._create_production()
        production._capture_product(
            self.finished, 2.0, lot=lot, result_package=self.package_1
        )
        production._capture_product(
            self.finished, 3.0, lot=lot, result_package=self.package_2
        )
        self._mark_done(production)
        quants = self.Quant._gather(self.finished, self.stock_location)
        self.assertEqual(
            {(quant.lot_id, quant.package_id, quant.quantity) for quant in quants},
            {(lot, self.package_1, 2.0), (lot, self.package_2, 3.0)},
        )

    def test_undo_finished(self):
        production = self._create_production()
        finished_move = self._move(production.move_finished_ids, self.finished)
        production._capture_product(self.finished, 3.0, result_package=self.package_1)
        production._capture_product(self.finished, 2.0, result_package=self.package_2)
        production._capture_undo_finished(1.0, result_package=self.package_1)
        self.assertEqual(production.qty_producing, 4.0)
        self.assertEqual(
            {(ml.result_package_id, ml.quantity) for ml in finished_move.move_line_ids},
            {(self.package_1, 2.0), (self.package_2, 2.0)},
        )
        production._capture_undo_finished(2.0, result_package=self.package_2)
        self.assertEqual(finished_move.move_line_ids.result_package_id, self.package_1)
        production._capture_undo_finished(2.0, result_package=self.package_1)
        # Nothing captured: back to the quantity of the order, as Odoo shows it
        self.assertEqual(production.qty_producing, 0.0)
        self.assertEqual(finished_move.quantity, 5.0)
        self.assertFalse(finished_move.move_line_ids.result_package_id)

    def test_capture_finished_lot(self):
        self.finished.tracking = "lot"
        lot = self.env["stock.lot"].create(
            {"name": "MRP-CAPTURE-LOT1", "product_id": self.finished.id}
        )
        other_lot = self.env["stock.lot"].create(
            {"name": "MRP-CAPTURE-LOT2", "product_id": self.finished.id}
        )
        production = self._create_production()
        production._capture_product(self.finished, 5.0, lot=lot)
        self.assertEqual(production.lot_producing_ids, lot)
        with self.assertRaises(UserError):
            production._capture_product(self.finished, 1.0, lot=other_lot)
        self._mark_done(production)
        self.assertEqual(lot.product_qty, 5.0)

    def test_capture_component_consumes_only_what_is_captured(self):
        production = self._create_production()
        move_a = self._move(production.move_raw_ids, self.component_a)
        production._capture_product(self.component_a, 3.0)
        captured = move_a.move_line_ids.filtered("picked")
        self.assertEqual(captured.quantity, 3.0)
        self.assertEqual(
            move_a.move_line_ids.filtered(lambda ml: not ml.picked).quantity, 7.0
        )
        self.assertEqual(self._reserved(self.component_a), 10.0)
        production._capture_product(self.finished, 5.0)
        # The captured component is kept when the quantity to produce changes
        self.assertEqual(move_a.quantity, 10.0)
        self.assertEqual(captured.quantity, 3.0)
        action = production.button_mark_done()
        self.assertEqual(action["res_model"], "mrp.consumption.warning")
        warning = Form(
            self.env[action["res_model"]].with_context(**action["context"])
        ).save()
        self.assertEqual(
            warning.mrp_consumption_warning_line_ids.filtered(
                lambda line: line.product_id == self.component_a
            ).product_consumed_qty_uom,
            3.0,
        )
        warning.action_confirm()
        self.assertEqual(production.state, "done")
        self.assertEqual(self.component_a.qty_available, 97.0)
        # Components not captured are consumed as the bill of materials says
        self.assertEqual(self.component_b.qty_available, 95.0)

    def test_capture_byproduct_produces_only_what_is_captured(self):
        production = self._create_production()
        production._capture_product(self.finished, 5.0)
        byproduct_move = self._move(production.move_byproduct_ids, self.byproduct)
        self.assertEqual(byproduct_move.quantity, 5.0)
        production._capture_product(self.byproduct, 2.0, result_package=self.package_1)
        self._mark_done(production)
        self.assertEqual(byproduct_move.quantity, 2.0)
        self.assertEqual(self.byproduct.qty_available, 2.0)
        quant = self.Quant._gather(self.byproduct, self.stock_location)
        self.assertEqual(quant.package_id, self.package_1)

    def test_capture_component_not_in_the_order(self):
        production = self._create_production()
        production._capture_product(self.finished, 5.0)
        line = production._capture_product(self.component_c, 1.0)
        self.assertEqual(line.move_id.raw_material_production_id, production)
        self.assertTrue(line.picked)
        self._mark_done(production)
        self.assertEqual(self.component_c.qty_available, 99.0)

    def test_capture_screen(self):
        self.env.user.group_ids |= self.env.ref("stock.group_production_lot")
        self.finished.write({"tracking": "lot", "barcode": "MRP-FINISHED"})
        self.component_a.barcode = "MRP-FISH"
        self.byproduct.barcode = "MRP-TRIMMINGS"
        production = self._create_production(quantity=2)
        production.picking_type_id.use_create_lots = True
        action = production.action_capture_open()
        session = self.env[action["res_model"]].browse(action["res_id"])
        session.capture_barcode("MRP-FISH")
        self.assertEqual(
            self._move(production.move_raw_ids, self.component_a).captured_quantity, 1
        )
        # The lot read for the product to manufacture is created
        session.capture_barcode("MRP-FINISHED")
        session.capture_barcode("MRP-LOT-1")
        self.assertEqual(production.lot_producing_ids.name, "MRP-LOT-1")
        self.assertEqual(production.qty_producing, 1)
        session.capture_barcode("MRP-TRIMMINGS")
        self.assertEqual(production.move_byproduct_ids.captured_quantity, 1)
        self.assertTrue(session.can_validate)

    def test_capture_screen_validate(self):
        self.finished.barcode = "MRP-FINISHED"
        self.component_a.barcode = "MRP-FISH"
        self.component_b.barcode = "MRP-TRAY"
        self.byproduct.barcode = "MRP-TRIMMINGS"
        production = self._create_production(quantity=1)
        action = production.action_capture_open()
        session = self.env[action["res_model"]].browse(action["res_id"])
        action = session.action_open_document()
        self.assertEqual(action["res_model"], "mrp.production")
        self.assertEqual(action["res_id"], production.id)
        for barcode in ("MRP-FINISHED", "MRP-FISH", "MRP-FISH", "MRP-TRAY"):
            session.capture_barcode(barcode)
        session.capture_barcode("MRP-TRIMMINGS")
        action = session.action_validate()
        self.assertEqual(production.state, "done")
        # The screen goes back to the order
        self.assertEqual(action["res_model"], "mrp.production")
        self.assertEqual(action["res_id"], production.id)

    def test_capture_on_finished_move(self):
        """Screens capturing on the finished move (e.g. weighing) produce"""
        production = self._create_production(quantity=5)
        move = production._capture_finished_move()
        self.assertEqual(move.capture_state, "to_capture")
        lines = move._capture_quantity(2, merge=False, result_package=self.package_1)
        self.assertEqual(production.qty_producing, 2)
        self.assertEqual(lines.result_package_id, self.package_1)
        self.assertEqual(move.captured_quantity, 2)
        self.assertEqual(move.capture_state, "capturing")
        # A weight recorded again on the line replaces the one captured
        lines._capture_set_quantity(3)
        self.assertEqual(production.qty_producing, 3)
        self.assertEqual(move.move_line_ids.filtered("result_package_id").quantity, 3)
        move._capture_quantity(2)
        self.assertEqual(production.qty_producing, 5)
        self.assertEqual(move.capture_state, "captured")
        unpacked = move.move_line_ids.filtered(lambda ml: not ml.result_package_id)
        self.assertEqual(unpacked._capture_finished_quantity(), 2)
        unpacked._capture_set_quantity(1)
        self.assertEqual(production.qty_producing, 4)
        move.action_capture_undo()
        self.assertEqual(production.capture_qty_producing, 0)
        move.action_capture_remaining()
        self.assertEqual(production.qty_producing, 5)

    def test_capture_finished_line_per_capture(self):
        """Without merging, each capture of the product to manufacture keeps a
        line of its own, e.g. one per weighing to label it"""
        production = self._create_production(quantity=5)
        move = production._capture_finished_move()
        first = move._capture_quantity(2, merge=False)
        second = move._capture_quantity(1.5, merge=False)
        self.assertNotEqual(first, second)
        self.assertEqual(production.qty_producing, 3.5)
        self.assertEqual((first | second).mapped("quantity"), [2, 1.5])
        # Removing a capture keeps the others
        first._capture_set_quantity(0)
        self.assertFalse(first.exists())
        self.assertEqual(production.qty_producing, 1.5)
        second._capture_set_quantity(2.5)
        self.assertEqual(production.qty_producing, 2.5)
        # What was captured is produced, whatever was set by hand
        production.qty_producing = 5
        self._mark_done(production)
        self.assertEqual(move.quantity, 2.5)
        self.assertEqual(move.move_line_ids, second)
