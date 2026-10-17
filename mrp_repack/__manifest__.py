# Copyright 2026 Tecnativa - Carlos Dauden
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "MRP Repack",
    "summary": "Repack a product with manufacturing orders that add the time spent "
    "to its cost",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/Manufacturing",
    "website": "https://github.com/OCA/manufacture",
    "author": "Tecnativa, Odoo Community Association (OCA)",
    "maintainers": ["carlosdauden"],
    "development_status": "Alpha",
    "license": "AGPL-3",
    "depends": ["mrp_account"],
    "data": [
        "data/ir_actions_server.xml",
        "views/stock_picking_type_views.xml",
    ],
}
