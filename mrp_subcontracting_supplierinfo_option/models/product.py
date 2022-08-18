# Copyright 2022 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _prepare_sellers(self, params=False):
        res = super()._prepare_sellers(params)
        if params and params.get("route_ids"):
            subcontractor_mto_route = self.env.ref(
                "mrp_subcontracting.route_resupply_subcontractor_mto"
            )
            if any(
                route == subcontractor_mto_route for route in params.get("route_ids")
            ):
                res = res.filtered(lambda x: not x.without_subcontracting)
            else:
                res = res.filtered(lambda x: x.without_subcontracting)
        return res

    def _select_seller(
        self, partner_id=False, quantity=0.0, date=None, uom_id=False, params=False
    ):
        if self.env.context.get("route_ids"):
            params = {} if not params else params
            params.update({"route_ids": self.env.context.get("route_ids")})
        return super()._select_seller(
            partner_id=partner_id,
            quantity=quantity,
            date=date,
            uom_id=uom_id,
            params=params,
        )
