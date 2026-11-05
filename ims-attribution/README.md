# IMS Measurement — installation candidate 1.0

Prepared for Insight Media Stream. Launch scope: Google, Meta and Simpli.fi, with Shopify, registered incremental measurement, CTV household association and client-safe Looker Studio output. Source and generated installation assets are supplied; account setup and live acceptance remain operator work. See RELEASE-1.0.md for exact tested boundaries and optional extensions.

## Start here

**Begin with [INSTALL-FIRST.md](INSTALL-FIRST.md)**. It supersedes earlier broad engineering-scope estimates. Run build_assets.py, configure your installation JSON, generate the deployment bundle and follow the installed acceptance checklist.

- [Business and technical design](docs/DESIGN.md)
- [Installation and operations](docs/INSTALL.md)
- [Server GTM configuration](docs/GTM.md)
- [Development quote scope and acceptance criteria](docs/DEVELOPER-BRIEF.md)
- [API and data contracts](docs/API.md)
- [CTV household/IP measurement](docs/CTV.md)
- [Implementation status and limitations](docs/STATUS.md)
- [All-platform connector contract](docs/ALL-PLATFORMS.md)
- [Looker Studio report specification](reporting/looker-studio-spec.md)
- [Installation release notes](docs/RELEASE-1.0.md)

## What the code does

- Tenant-scoped authenticated API, agency console, separate agency/client credentials.
- Consent-gated first-party browser journey collection; server GTM forwarding source included.
- Shopify HMAC-verified paid-order and merchandise-refund ingestion; browser observations never create revenue.
- Order-level deduplication, refund restatement, late identity linkage, 30-day lookback.
- First non-direct, last non-direct, linear and 40/20/40 position-based attribution.
- Effective-dated channel markup and correctly recalculated client-facing ROAS, CPA, CPC and CPM.
- Daily campaign spend imports, Google/Meta spend fetchers, client-safe NDJSON/BigQuery export jobs.
- Signed universal connector ingestion with capability restrictions, campaign/account namespaces, replay validation and configurable vendor CSV mapping.
- Shopify historical/rolling GraphQL reconciliation, authoritative net snapshots, supervised job pipeline, safe freshness/status output, backup verification and key issuance/revocation.
- Registered randomized customer/geo-cluster holdouts, immutable assignment, zero-outcome units, lift, bootstrap confidence intervals, permutation p values, sample-ratio checks and incremental ROAS.
- Persistent conversion-forwarding outbox with retries to an sGTM gateway, requiring verified order plus observed marketing consent.
- CTV exact-IP association with per-client HMAC identifiers, separate view-through reporting, and IP-defined randomized holdout enrollment/outcome sync.

## Local test and demo

Requires Python 3.11+ (3.12 recommended); Node 20+ for SDK tests only.

```bash
python3 -m unittest discover -s tests -v
node --test tests/pixel.test.cjs
node --test tests/assets.test.cjs
python3 examples/demo.py
python3 examples/start_demo.py
```

The demo uses synthetic data and writes only to a temporary database. It sends no advertising events. Production uses Gunicorn, installed from requirements.txt. No npm packages are needed.

## Important product decisions

Shopify is the first live store integration target. BigCommerce and WooCommerce can use the canonical trusted-import API; automatic order/refund adapters for those platforms are additional development. The previous pixel package is preserved under `legacy/` for its store adapter references, not automatically installed or silently merged. Do not run both old and new conversion senders for the same destination without an agreed deduplication strategy.

GTM server-side manages tag processing and destination routing. It is not the database, attribution engine or incrementality engine. Importable templates and a bundled Shopify installer are provided under dist/. Account-specific checkout/order settings and live validation are still required.

Native Google Ads/Meta/Simpli.fi conversion delivery is not guaranteed merely by forwarding to sGTM. Configure approved vendor tags, matching identifiers, consent, timestamps and duplicate handling; validate acceptance in each platform. Simpli.fi requires its actual account-specific supported interface. See STATUS.md.

Software subscriptions can be kept low, but hosting, server GTM, warehouse usage, implementation and maintenance are not necessarily free. Hosting performance at the previously estimated client traffic has not been load-tested.
