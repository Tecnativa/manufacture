# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo.tests import Form, common


class TestMrpSubcontractingBomDualUse(common.SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buy_route = cls.env.ref("purchase_stock.route_warehouse0_buy")
        cls.subcontractor_mto_route = cls.env.ref(
            "mrp_subcontracting.route_resupply_subcontractor_mto"
        )
        cls.partner = cls.env["res.partner"].create({"name": "Mr Odoo"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test product",
                "type": "product",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "name": cls.partner.id,
                            "min_qty": 1,
                            "price": 5,
                            "without_subcontracting": True,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": cls.partner.id,
                            "min_qty": 1,
                            "price": 10,
                        },
                    ),
                ],
                "route_ids": [
                    (6, 0, [cls.buy_route.id, cls.subcontractor_mto_route.id])
                ],
            }
        )
        cls.component_a = cls.env["product.product"].create({"name": "Test Comp A"})
        cls.bom = cls._create_bom(cls)
        cls.purchase_order_model = cls.env["purchase.order"]

    def _create_bom(self):
        mrp_bom_form = Form(self.env["mrp.bom"])
        mrp_bom_form.product_tmpl_id = self.product.product_tmpl_id
        mrp_bom_form.type = "subcontract"
        mrp_bom_form.subcontractor_ids.add(self.partner)
        mrp_bom_form.product_tmpl_id = self.product.product_tmpl_id
        with mrp_bom_form.bom_line_ids.new() as line_form:
            line_form.product_id = self.component_a
            line_form.product_qty = 1

        return mrp_bom_form.save()

    def _product_replenish(self, product, qty, route):
        replenish_form = Form(
            self.env["product.replenish"].with_context(default_product_id=product.id)
        )
        replenish_form.quantity = qty
        replenish_form.route_ids.add(route)
        replenish = replenish_form.save()
        replenish.launch_replenishment()

    def test_product_replenish_buy(self):
        self._product_replenish(self.product, 1, self.buy_route)
        po = self.purchase_order_model.search([("partner_id", "=", self.partner.id)])
        self.assertEqual(po.order_line.price_unit, 5)

    def test_product_replenish_subcontracting(self):
        self._product_replenish(self.product, 1, self.subcontractor_mto_route)
        po = self.purchase_order_model.search([("partner_id", "=", self.partner.id)])
        self.assertEqual(po.order_line.price_unit, 10)
