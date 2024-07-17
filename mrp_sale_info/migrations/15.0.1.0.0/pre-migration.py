# Copyright 2024 Tecnativa - David Vidal
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # Create fake table for not triggering the compute method
    openupgrade.logged_query(
        env.cr,
        """
        CREATE TABLE mrp_production_sale_order_line_rel
        (sale_order_line_id INTEGER, mrp_production_id INTEGER)
        """,
    )
