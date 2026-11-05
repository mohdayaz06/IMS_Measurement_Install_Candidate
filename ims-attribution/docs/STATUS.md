# Installation candidate 1.0 status

## Supplied implementation for the scoped launch

- Tenant-isolated order/refund ledger, effective markup and four attribution models.
- Signed Shopify paid/refund/privacy webhooks and paginated GraphQL reconciliation.
- Bundled Shopify custom pixel and first-party SDK; importable server GTM client/tag templates.
- Google/Meta spend jobs; native Google click-import/Meta CAPI sender option; alternative configured sGTM native tag route.
- Actual account-tag Simpli.fi browser adapter; automated scheduled CSV/HTTPS spend and approved CTV/network feed processing.
- Registered randomized experiments, CTV IP association, both-arm outcome sync/net restatement and approved safe publication.
- Looker Community Connector, safe field projection/client credential enforcement, optional BigQuery publisher and chart/formula specifications.
- Single-install configuration generator, API/jobs Compose services, scheduler with due intervals, online backup rotation, operational status and preflight.
- Key issuance/revocation, trusted visitor consent blocks, signed merchant privacy requests and local redaction/closure operations.

## Operator/account configuration and acceptance

Hosting/DNS/TLS; secrets; merchant app scopes/API versions; server GTM import/settings/native vendor tags/Preview; Shopify checkout and financial reconciliation; account-specific Simpli.fi reports/tags/viewer-log permissions; actual DSP control exclusions; Apps Script/Looker deployment and sharing; WAF/admin access, off-host backups and real-load test. The package does not claim those account operations have happened.

## Optional expansions outside the install-only launch scope

Additional ad platforms/native adapters, distributed PostgreSQL/queue/HA, staff SSO/admin-user product, probabilistic person identity, MMM, synthetic controls, predictive LTV/product-profitability suite, and a distributed Shopify app marketplace product. BigCommerce/WooCommerce reference adapters remain optional; inspect unsupported amount-only refund/merchant allocation cases before enablement.

## Validation limits

Python backend/dataflow tests and Node SDK/GTM/connector mock tests run locally. Docker and PHP runtimes are not installed here; production image build and optional PHP plugin execution are not claimed. No real Shopify checkout, Google/Meta API receipt, Simpli.fi log export, GTM publish or Looker account deployment has been performed. See TEST-RESULTS.md and LAUNCH-ACCEPTANCE.md.

Network/IP association is separate from causal incrementality. Raw IPs are transformed into per-tenant HMAC identifiers at trusted ingestion, not published to client reporting. A provider must supply real viewer impression records and the merchant must provide authorized conversion-network signals. Browser-only exposed cohorts do not create a valid unexposed control group.

Direct Google click imports require current eligible developer-token/conversion-action access; the server GTM website-tag route is the alternative when unsupported. Missing identifiers, vendor errors and gateway responses are not counted as attributed sales. Merchant ledger revenue remains independent.

This is a scoped installation candidate, not a claim of universal live integration certification or complete Triple Whale parity. Run INSTALL-FIRST.md and LAUNCH-ACCEPTANCE.md before production cutover.
