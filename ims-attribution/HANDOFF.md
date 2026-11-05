# IMS Measurement Platform — developer handoff

Installation candidate 1.0 · Prepared 4 November 2026 · Owner: Insight Media Stream

**Current install path: INSTALL-FIRST.md.** Google/Meta/Simpli.fi is the launch scope. The release now supplies GTM import assets, bundled Shopify pixel, native senders, scheduled report adapters, deployment generator and Looker connector. The broader optional product requirements below are background; use docs/DEVELOPER-BRIEF.md for the scoped installation quote.

## What IMS is commissioning

An IMS-owned, platform-independent measurement system combining a universal tracking installation, verified ecommerce revenue, cross-channel attribution, CTV household association, randomized incremental campaign measurement, private agency pricing and automated client reporting in Looker Studio.

“All ad platforms” means a common measurement engine and extensible connector contract. It does not imply that every vendor provides the same API, matching data, log-export permissions or native conversion endpoint. Platform support must be accepted capability by capability.

## Package map

| Location | What the developer receives |
|---|---|
| ims/ | WSGI API, SQLite schema, order ledger, attribution, pricing, CTV, experiment, connector, privacy and operations modules |
| web/ | Consent-gated SDK and agency/client console |
| integrations/ | Server GTM template source, Shopify reference pixel, Shopify GraphQL reconciliation, Google/Meta spend jobs, signed universal CSV sender, conversion outbox, pipeline runner and BigQuery publisher |
| deploy/ | Docker configuration is at root; reverse proxy and systemd scheduling examples are here |
| reporting/ | Client report layout, formulas, safe data-source boundaries |
| docs/ALL-PLATFORMS.md | Connector contract and capability matrix |
| docs/DESIGN.md | Architecture and measurement policy |
| docs/API.md | Core payloads and endpoints |
| docs/CTV.md | IP association, data dependencies and randomized CTV testing |
| docs/DEVELOPER-BRIEF.md | Quote scope and production acceptance criteria |
| docs/INSTALL.md | Deployment instructions and runbook |
| docs/STATUS.md | Boundaries and remaining production work |
| tests/ | Synthetic backend, connector, reconciliation, CTV, HTTP and SDK tests |
| legacy/ | Prior pixel archive for reference; do not deploy in parallel blindly |

## Quick review in 15 minutes

1. Run `python3 -m unittest discover -s tests -v` and `node --test tests/pixel.test.cjs` from project root. No Python packages are required for these tests.
2. Run `python3 examples/demo.py` for a no-network money/markup demonstration.
3. Run `python3 examples/start_demo.py`, open the loopback URL, and use the temporary agency token printed to the terminal. Compare client-token response. This server and database are synthetic and ephemeral; not production.
4. Review ALL-PLATFORMS.md and STATUS.md before quoting live integrations. No live accounts or infrastructure are provisioned.
5. Review DEVELOPER-BRIEF.md and return line-item implementation/deployment/maintenance estimates with assumptions and exclusions.

## Supplied functional behavior

- One independently verified order ledger per tenant, browser identity observations separated from revenue, idempotent paid/refund webhook handling.
- First/last non-direct, linear, position-based credit; common lookback; unattributed remains visible.
- Per-channel effective-dated markup and client-safe cost/ROAS/CPA/CPC/CPM; agency-only raw cost fields.
- Native Google/Meta spend-fetcher source plus generic signed all-platform ingestion and CSV mapping/aggregation.
- Server GTM ingress/egress source, consent-gated conversion outbox with stable event IDs and retry state.
- CTV exact-network association, protected IP keys, one last eligible impression per order per selected window, separate association report.
- Registered randomized customer, IP-network or geo-cluster experiments; ITT analysis, zero-conversion units, confidence intervals, permutation checks and iROAS input.
- Shopify GraphQL historical/rolling reconciliation using current net subtotal snapshots; avoids subtracting already included refunds twice.
- Supervised scheduled jobs, safe freshness status, backup/integrity verification, scoped key issuance/revocation and trusted consent withdrawal.
- Client-safe BigQuery export with strict allowed fields; dashboard/formula specification for Looker Studio.

## Important definitions

Revenue: merchant merchandise subtotal/net policy, not vendor-reported “sales.” Shopify snapshots use currentSubtotalPriceSet; verify tax-inclusive shop settings and adjustments against actual merchant reports. Purchase count remains purchase events, even if an order is later fully refunded. Cross-currency conversion is not implemented.

CTV conversion association: a verified purchase and eligible logged impression share a protected exact-IP network signal. It is not proof of a particular person's exposure/attention and is not causal lift. A purchase may also appear in click-attribution reports; never add both views.

Incrementality: a preregistered randomized test with campaign-side control exclusion, an independent complete outcome source and sufficient statistical power. Hash assignment inside this service does not itself enforce DSP suppression. IMS's operating process and the developer's suppression/outcome integrations are part of deployment acceptance.

Client media cost: agency billable media amount using configured markup; raw vendor cost and pricing rules never enter client exports. A client who independently owns ad-account billing access may still see that account's vendor cost. Software cannot make their separate access disappear.

## Requested deployment architecture

Pilot on one durable Linux host (including AWS if IMS prefers), TLS/WAF, encrypted disk, single-instance Gunicorn/SQLite, scheduled jobs, managed secrets, off-host backups; independently hosted server GTM; BigQuery client-safe reporting datasets; Looker Studio client reports. AWS hosting does not require abandoning server GTM/BigQuery, but cross-cloud egress/cost and credentials must be quoted. For HA/large multi-client scale migrate to PostgreSQL + durable queue before rollout; do not run SQLite on ephemeral autoscaled disks.

## Required access, supplied by IMS/merchant

- DNS and hosting/cloud projects owned by IMS, server GTM/web GTM administration.
- Merchant Shopify app/API scopes, approved customer/consent/privacy implementation, order fixtures and financial reconciliation definition.
- Ad-account reporting/API permissions, supported API versions, UTM conventions, native conversion-action/pixel IDs.
- CTV DSP confirmation of actual viewer-level impression logs, measurement/data rights, compatible network IDs and treatment/control exclusion capabilities. If unavailable, quote geo-based experimental design instead of promising unsupported IP exports.
- BigQuery client dataset/reporting identities, Looker Studio sharing expectations, retention and operational service targets.

## What remains before production

Live account configuration/validation, approved Shopify production app/pixel strategy and checkout linkage, commerce privacy/deletion webhooks and full lifecycle, vendor-specific optimization tag schemas/matching, Simpli.fi and other requested native adapters, rate-limit/transient retry tuning, staff SSO/MFA, production monitoring and load testing, report assembly, reviewed experiment aggregate publication and actual holdout enforcement. See STATUS.md for current source vs live dependency distinctions.

This is an install-and-validate software candidate for the scoped pilot, with optional expansion designs retained. Separate account configuration/live acceptance from optional new product development and any defects found in the code. No unverified claim of complete Triple Whale feature parity is authorized.

## Suggested delivery gates

1. Source review + sample-data agreement: confirm order/cost policy and all-platform capability matrix.
2. Staging: run supplied tests, provision isolated tenant, verify secrets/IAM/backups and signed connectors.
3. Merchant validation: reconcile paid/refunded/edited/test orders, consent, checkout identity and campaign keys.
4. Reporting validation: demonstrate markup and denominator calculations with client access; no raw costs in reports/downloads.
5. CTV validation: verify impression provenance, usable viewer network data, windows and overlap; register and enforce pilot holdout.
6. Live acceptance: native destination diagnostics, 7–14 day parallel ledger reconciliation, load/restore tests, alerting and handover. Roll back destinations without discarding verified order history.

Provide an estimate and schedule for each gate, fixed-price assumptions, recurring infrastructure/support costs and third-party license dependencies. Do not bundle a new attribution SaaS license without IMS approval.
