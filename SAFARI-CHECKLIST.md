# Safari local acceptance

The Release app was built on this Mac and verified with `codesign --verify --deep --strict`. The ZIP contains a self-contained ad-hoc signed development app. No Apple distribution identity was available. The user explicitly approved enabling Safari’s Allow unsigned extensions setting and authenticated locally; it is now on. The built containing app launched successfully, but the extension was not enabled and no website access was granted. Further Safari interaction stopped at the user’s request to focus on codebase basics.

## Start

1. Unzip **Gift Card Discounts.zip** beside this source folder and open the app.
2. For this development build, Safari Developer settings must allow unsigned extensions. This applies globally to development extensions; decide whether to enable it yourself. A proper Apple-signed build avoids that development setting.
3. Enable Gift Card Discounts in Safari Settings > Extensions and grant access to the retailer sites you want to test.
4. Open its toolbar popup. Either enable synthetic demo data, or enter the deployed HTTPS snapshot URL with demo mode off. The bundled app has no live feed configured.

## Required checks still unrun in actual Safari

- Demo mode shows a clearly marked pill on `https://www.dominos.com`; demo links cannot initiate purchases.
- Opening an alias/subdomain or another tab for that retailer shows no second pill in the same Safari session.
- Background worker suspension/recreation preserves session deduplication; quitting/reopening Safari resets it.
- Dismiss, 24-hour snooze, permanent hiding, restoration, and manual refresh work.
- Failed refresh retains fresh cached offers; expired offers and no-inventory retailers show no pill.
- Keyboard controls, Escape, narrow windows, retailer layout, and dark mode remain usable without focus theft.
- Live mode rejects synthetic snapshots. A deployed feed shows real advertised percentages with observation times and the before-fees qualifier.

The Chromium preview checks and mocked worker tests exercise shared code but do not establish these Safari results. No checkout, card purchase, or payment interaction is part of acceptance.
