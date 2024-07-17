# Copyright 2024 Tecnativa - David Vidal
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import deque

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # Drop the previous fake table and create correctly all the relations through ORM
    openupgrade.logged_query(
        env.cr, """DROP TABLE IF EXISTS mrp_production_sale_order_line_rel"""
    )
    env.registry._post_init_queue = deque()
    SaleOrderLine = env["sale.order.line"]
    SaleOrderLine._fields["created_production_ids"].update_db(SaleOrderLine, False)
