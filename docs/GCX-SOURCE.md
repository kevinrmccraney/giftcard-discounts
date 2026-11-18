# Public GCX collection

Verified on 2026-10-24: an ordinary unauthenticated HTTPS GET of the [public catalog](https://gcx.app/buy-gift-cards) returned HTML product cards and numbered pagination. The collector parses the displayed “Up to …% off” text; GCX Cash is a separate promotional reward and is excluded. No login, purchases, private API, credentials or browser automation is required.

The catalog advertises maximum discounts. These are possible savings before fees, not a checkout quote or verified card inventory. Counts, total available face value and average discounts remain unknown. The snapshot preserves `observation_kind: catalog_advertised`. Its timestamp is collection start time, and normal expiry still applies. Denominations, redemption restrictions and minimum order constraints must be checked on the provider page.

The [official Buyer Protection Fee schedule](https://help.raise.com/hc/en-us/articles/37889255719060-Buyer-Protection-Fee) charges a percentage of savings, with rates depending on discount range. Published ranges leave fractional boundaries unspecified, so the collector does not invent an exact fee or net purchase cost. [GCX terms](https://gcx.app/terms) and the provider's source policy remain relevant to production operation.

Collection fails without replacing the current snapshot when a mapped retailer is absent, markup changes, pagination repeats brands, the request budget expires, or access is denied/rate limited. Absence is never translated into zero inventory. Defaults: maximum 20 pages/20 attempts, 20-second request timeout, one-second spacing and at most two retries for transient failures. HTTP 401, 403 and 429 stop immediately; redirects stop immediately. Maximum response size is 2 MB. All collection is sequential.

`fixtures/gcx-catalog-captured.html` is a sanitized three-card excerpt refreshed from the public catalog on 2026-11-17, with scripts, tracking attributes and images removed. It is not a complete catalog or synthetic inventory. Percentages in the fixture change over time; mutation tests exercise drift, missing retailers, reward-only offers, repeated pages and request limits.

`config/retailers-live.json` covers 11 retailers. Added merchant domains were reviewed directly through their public homepages: [Walmart](https://www.walmart.com), [Best Buy](https://www.bestbuy.com), [The Home Depot](https://www.homedepot.com), [Macy's](https://www.macys.com), [Airbnb](https://www.airbnb.com), [DoorDash](https://www.doordash.com), [Chipotle](https://www.chipotle.com), [Ulta](https://www.ulta.com). Original Domino's, Starbucks and Lowe's mappings are retained. Brand paths come from real GCX catalog links rather than inferred brand names. The three-retailer `config/retailers.json` stays compatible with synthetic demo fixtures.

Run from the project directory:

```sh
python3 -m giftcard_tool collect --catalog config/retailers-live.json --output build/live/input.json
python3 -m giftcard_tool import build/live/input.json --catalog config/retailers-live.json --output build/live/snapshot.json --database build/live/history.sqlite3
```
