This module records on manufacturing orders the quantities read or weighed by the user, using the engine of `stock_capture`. It has no screen of its own.

- **Product to manufacture:** a captured quantity adds to the quantity to produce and its lot becomes the lot to produce, as Odoo's barcode application does. The finished move is not picked, because Odoo would take it as already produced. A quantity captured into a destination package gets its own finished line in that package, and changing the quantity to produce keeps those lines.
- **Components:** a captured quantity is taken from the reservation of the component, keeping the rest reserved. Odoo then keeps the captured quantity when the quantity to produce changes, and components not captured are consumed as the bill of materials says. A component not in the order gets a new move.
- **Byproducts:** only the captured quantity is produced for a byproduct with captured quantities.

When the order is marked as done, the lines left unpicked on the moves with captured quantities are dropped before the consumption warning, so the warning compares what was captured with the bill of materials.
