# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, freeze_time, tagged


@tagged("post_install", "-at_install")
class TestMrpRepack(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.workcenter = cls.env["mrp.workcenter"].create(
            {"name": "Weighing", "costs_hour": 30.0}
        )
        cls.repack_type = cls.warehouse.manu_type_id.copy(
            {
                "name": "Repacking",
                "sequence_code": "RPK",
                "repack": True,
                "repack_workcenter_id": cls.workcenter.id,
            }
        )
        category = cls.env["product.category"].create(
            {"name": "Average cost", "property_cost_method": "average"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Hake",
                "is_storable": True,
                "tracking": "lot",
                "uom_id": cls.env.ref("uom.product_uom_kgm").id,
                "categ_id": category.id,
                "standard_price": 10.0,
            }
        )
        # The older lot would be reserved first without the lot to repack
        cls.lot_other = cls._create_lot_in_stock("REPACK-OLD", 5.0)
        cls.lot = cls._create_lot_in_stock("REPACK-LOT", 10.0)

    @classmethod
    def _create_lot_in_stock(cls, name, quantity):
        lot = cls.env["stock.lot"].create({"name": name, "product_id": cls.product.id})
        cls.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": cls.product.id,
                "location_id": cls.stock_location.id,
                "lot_id": lot.id,
                "inventory_quantity": quantity,
            }
        ).action_apply_inventory()
        return lot

    def _quant(self, lot):
        return self.env["stock.quant"]._gather(
            self.product, self.stock_location, lot_id=lot, strict=True
        )

    def _repack(self, lot):
        action = self._quant(lot).action_repack()
        return self.env["mrp.production"].browse(action["res_id"])

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

    def test_repack_order_from_quant(self):
        production = self._repack(self.lot)
        self.assertEqual(production.picking_type_id, self.repack_type)
        self.assertEqual(production.state, "confirmed")
        self.assertEqual(production.product_qty, 10.0)
        self.assertEqual(production.lot_producing_ids, self.lot)
        raw_move = production.move_raw_ids
        self.assertEqual(raw_move.product_id, self.product)
        self.assertEqual(raw_move.move_line_ids.lot_id, self.lot)
        self.assertEqual(raw_move.quantity, 10.0)
        # The consumption is valued before the production
        self.assertLess(raw_move.id, min(production.move_finished_ids.ids))
        self.assertEqual(production.workorder_ids.workcenter_id, self.workcenter)

    def test_repack_adds_the_time_spent_to_the_cost(self):
        production = self._repack(self.lot)
        workorder = production.workorder_ids
        with freeze_time("2026-10-01 09:00:00"):
            workorder.button_start()
        production_form = Form(production)
        production_form.qty_producing = 9.8
        production_form.save()
        with freeze_time("2026-10-01 10:00:00"):
            workorder.button_finish()
        self.assertEqual(workorder.duration, 60.0)
        self._mark_done(production)
        quants = self._quant(self.lot)
        self.assertEqual(sum(quants.mapped("quantity")), 10.0)
        # 15 kg at 10.0 (150.0), 9.8 kg consumed (98.0) and produced with the
        # hour of the work center added (98.0 + 30.0)
        self.assertAlmostEqual(self.product.standard_price, 12.0)

    def test_order_with_the_product_added_after_creation(self):
        # Without operation, nothing makes Odoo recreate the finished move
        self.repack_type.repack_workcenter_id = False
        production_form = Form(self.env["mrp.production"])
        production_form.product_id = self.product
        production_form.picking_type_id = self.repack_type
        production_form.product_qty = 4.0
        production = production_form.save()
        production.action_confirm()
        raw_move = production.move_raw_ids
        self.assertEqual(raw_move.product_id, self.product)
        self.assertEqual(raw_move.product_uom_qty, 4.0)
        self.assertLess(raw_move.id, min(production.move_finished_ids.ids))
        self.assertEqual(len(production.move_finished_ids), 1)
        self.assertFalse(production.workorder_ids)

    def test_no_repacking_operation_type(self):
        self.repack_type.repack = False
        with self.assertRaises(UserError):
            self._quant(self.lot).action_repack()
