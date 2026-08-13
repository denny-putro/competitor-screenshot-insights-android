# Unknown App Discovery

Before asking the user to approve the discovery scope, briefly search the web to understand what the app is and its main purpose, then use that context to make the exploration plan more relevant. Begin the device workflow only after the user approves the business scope, the three-domain exploration budget, and the payment boundary.

## Build a feature map from the real interface

Inspect the home surface, primary navigation, categories, menus, search, recommendations, and meaningful capabilities revealed after one normal action. Record candidate functions with one of these states:

- `observed`: directly visible but not entered.
- `entered`: opened and supported by captured evidence.
- `inferred`: suggested by a label or entry but not verified.
- `blocked`: inaccessible because of login, permission, network, region, or state.
- `out_of_budget`: useful but outside this run.

Never describe `inferred` as verified. Do not invent specific page names before seeing them.

## Select up to three core domains

Rank domains by:

1. relevance to the user's research goal;
2. prominence as a primary entry;
3. coverage of a new user task;
4. evidence of a new interaction or decision state;
5. time and operation cost.

Avoid spending the budget on similar recommendation lists, marketing entries, or repeated detail pages. Actual entry names and page splits may change without new confirmation while the approved scope is unchanged.

## Capture balanced evidence

Target about 12 valid screenshots and never exceed 20. Across each selected domain, prefer:

- an entry or starting state;
- a result after one main action;
- a detail, selection, comparison, or decision state;
- one long screenshot when content spans viewports and sequence adds value.

Keep distinct functions, states, and outcomes even when some screenshots are not visually perfect. Do not reduce the set to a few polished images. Treat small readable seams, fixed-bar repetition, dynamic media, limited extent, or a usable viewport sequence as warnings rather than deletion reasons.

Stop entering new domains at three. Stop valid evidence at 20. Do not automatically create a coverage-driven second capture pass unless that behavior has been separately enabled. Keep visible but unentered functions labeled `observed` or `out_of_budget` for the handoff.

## Payment and completion

Entering a payment page ends the journey. Capture or read-only scroll there, record `payment_page_reached`, then back or close. Never interact with payment fields, methods, wallets, confirmation controls, or biometrics.

Finish with:

- the three selected domains and their states;
- the number of valid screenshots;
- any blocked, inferred, or out-of-budget functions;
- missing entry/result/detail states;
- page-bottom or extent limits for long captures.

Do not start a third domain expansion or another autonomous exploration round after the approved budget is exhausted.
