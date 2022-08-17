# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests import Form, common


class TestMrpSubcontractingResupplyLink(common.SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.subcontractor_mto = cls.env.ref(
            "mrp_subcontracting.route_resupply_subcontractor_mto"
        )
        cls.supplier = cls.env["res.partner"].create({"name": "Mr Odoo"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test product",
                "type": "product",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "name": cls.supplier.id,
                            "min_qty": 1,
                            "price": 10,
                        },
                    )
                ],
            }
        )
        cls.component = cls.env["product.product"].create(
            {
                "name": "Test Component",
                "route_ids": [(6, 0, [cls.subcontractor_mto.id])],
            }
        )
        cls.bom = cls._create_mrp_bom(cls)
        cls.purchase_order = cls._create_purchase_order(cls)
        spt_model = cls.env["stock.picking.type"].with_context(active_test=True)
        cls.picking_type_sbc = spt_model.search([("code", "=", "SBC")])

    def _create_mrp_bom(self):
        mrp_bom_form = Form(self.env["mrp.bom"])
        mrp_bom_form.product_tmpl_id = self.product.product_tmpl_id
        mrp_bom_form.type = "subcontract"
        mrp_bom_form.subcontractor_ids.add(self.supplier)
        with mrp_bom_form.bom_line_ids.new() as line_form:
            line_form.product_id = self.component
            line_form.product_qty = 1
        return mrp_bom_form.save()

    def _create_purchase_order(self):
        order_form = Form(self.env["purchase.order"])
        order_form.partner_id = self.supplier
        with order_form.order_line.new() as line_form:
            line_form.product_id = self.product
            line_form.product_qty = 1
        return order_form.save()

    def test_misc(self):
        self.purchase_order.button_confirm()
        self.assertEqual(self.purchase_order.picking_ids.mrp_production_count, 1)
        self.assertEqual(
            self.purchase_order.picking_ids.mrp_subcontracting_purchase_order_count, 0
        )
        production = self.env["mrp.production"].search([("bom_id", "=", self.bom.id)])
        res = self.purchase_order.picking_ids.action_view_mrp_productions()
        self.assertEqual(res["res_id"], production.id)
        self.assertEqual(production.picking_ids.mrp_production_count, 0)
        self.assertEqual(
            production.picking_ids.mrp_subcontracting_purchase_order_count, 1
        )
        res = production.picking_ids.action_view_mrp_subcontracting_purchase_orders()
        self.assertEqual(res["res_id"], self.purchase_order.id)
