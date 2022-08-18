# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.model
    def _prepare_purchase_order_line_from_procurement(
        self, product_id, product_qty, product_uom, company_id, values, po
    ):
        if values.get("route_ids"):
            _self = self.with_context(route_ids=values.get("route_ids"))
        else:
            _self = self
        return super(
            PurchaseOrderLine, _self
        )._prepare_purchase_order_line_from_procurement(
            product_id, product_qty, product_uom, company_id, values, po
        )

    @api.model
    def _prepare_purchase_order_line(
        self, product_id, product_qty, product_uom, company_id, supplier, po
    ):
        if self.env.context.get("route_ids"):
            product_id = product_id.with_context(
                route_ids=self.env.context.get("route_ids")
            )
        return super()._prepare_purchase_order_line(
            product_id, product_qty, product_uom, company_id, supplier, po
        )
