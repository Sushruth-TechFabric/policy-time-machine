# Genie answers questions; the app owns drill-down

Every question the user types goes to Databricks Genie, and the app renders the result by classifying its column shape (timeline-shaped, cohort-shaped, aggregate-shaped). Click-driven navigation does not: when a user clicks a policy result card, the app loads that policy's timeline with its own parameterized SQL against the semantic layer.

We split it this way because clicking a card is a lookup by known `policy_id`, not an analytical question — routing it through natural language would add latency and non-determinism to the product's signature visual with no interpretive value in return. Genie remains in the path for every actual question, which is where its value is.

## Consequences

- The policy timeline has a guaranteed column contract when reached by click, and a best-effort one when reached by question. The renderer must handle both.
- Result-shape classification is a first-class app concern and needs its own specification and tests.
- A reader who expects "Genie-powered" to mean "Genie is the only data path" will be surprised; this is deliberate.
