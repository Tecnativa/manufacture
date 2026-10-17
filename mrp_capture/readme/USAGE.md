Other modules capture quantities through:

- `mrp.production._capture_product(product, quantity, uom=None, lot=None, location=None, package=None, owner=None, result_package=None)`, which sends the product to the methods below
- `mrp.production._capture_finished(quantity, uom=None, lot=None, result_package=None)` and `mrp.production._capture_undo_finished(quantity, uom=None, result_package=None)` for the product to manufacture
- `mrp.production._capture_component(product, quantity, uom=None, **characteristics)` for components
- `stock.move.line._capture_undo(quantity=None)` of `stock_capture` for components and byproducts
