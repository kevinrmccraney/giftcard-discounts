# Fixtures

`demo-batch.json` is deliberately SYNTHETIC. It is our interchange schema, NOT a captured GCX JSON response. Names are illustrative; prices, discounts, quantities and availability are invented for tests. Do not use this fixture as shopping advice.

`demo: true` is preserved into the snapshot and must be visibly identified by every client. `python3 -m giftcard_tool demo` deliberately rebases this synthetic fixture's dates; the import command never changes an actual observation timestamp.

No authenticated sessions, gift-card numbers, cookies or personal records are included. The live GCX inventory API and retailer-specific average remain unverified.
