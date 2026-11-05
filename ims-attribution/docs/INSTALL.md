# Installation and operations

**Current release:** Start with INSTALL-FIRST.md and generated deployment files. This document retains lower-level/manual and optional BigQuery instructions; it is not a list of additional source development required for the scoped Google/Meta/Simpli.fi pilot.

## Prerequisites

Python 3.12, Node 20+ for tests, Docker Compose, a Linux host with durable encrypted disk, TLS reverse proxy, DNS access, merchant access, Google Cloud project, server GTM account, ad-account API access, and BigQuery/Looker Studio access. The bq CLI is needed on the export job runner. No infrastructure is provisioned by this archive.

## First local run

```bash
python3 -m unittest discover -s tests -v
node --test tests/pixel.test.cjs
python3 examples/demo.py
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Provision a client using a secure terminal. Read the Shopify app webhook secret into the environment from your secrets manager; never hardcode it into this archive. `shop_secret` is the app client secret used for webhook signatures, not the Shopify Admin API access token.

```bash
umask 077
export IMS_DB=/absolute/private/path/ims.sqlite3
python3 -m ims.cli create-tenant CLIENT_ID --origin https://shop.example.com --shop merchant.myshopify.com --timezone America/New_York > client-credentials.json
```

Record the returned agency, client and bridge credentials in a secrets manager and remove the temporary credential file after import. Client names/IDs are not secrets. The sample CLI provisions keys locally; production should add staff SSO/MFA, scoped service identities and a key-rotation UI. `revoke-key` accepts a SHA256 fingerprint.

Run locally on loopback:

```bash
.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 1 --threads 4 --timeout 120 'ims.app:application_factory()'
```

Open http://127.0.0.1:8080 and use the agency token for the console. The token is not saved to browser storage. Use a client token to verify restricted report output. HTTPS is mandatory for live use.

## Docker deployment

`docker compose up --build -d` runs the API with a durable named volume and loopback host binding. Provision the tenant inside the container using `docker compose exec attribution python -m ims.cli --db /data/ims.sqlite3 create-tenant ...`. Pass the Shopify secret securely to that process. Do not accidentally create the database on the host while the API reads a different container database.

The pilot is ONE API instance on ONE host. SQLite WAL is unsuitable for this design on network filesystems or ephemeral serverless disks. If horizontal scale or high availability is required, quote the PostgreSQL/queue migration before production.

Reverse proxy requirements: TLS, request-body limit <=1 MiB, path-specific rate limits for `/collect/`, bot/WAF rules, auth endpoint throttling, upstream timeout, private admin access where possible, no credential/body/query logging, and no caching of API responses. Apply explicit trusted origins. Do not use wildcard CORS. Shopify sandbox origins must be checked in a test store; never solve a blocked sandbox by broadly accepting `null` origins.

## Shopify

1. Create/install a merchant-authorized Shopify custom app with minimum required order/customer access. Subscribe HTTPS webhooks `orders/paid` and `refunds/create` to `https://tracking.example.com/shopify/CLIENT_ID`.
2. Configure exact `.myshopify.com` domain and webhook HMAC secret in tenant provisioning. Read topic/Shopify schema compatibility against the pinned app API version.
3. Install the reference custom pixel in Customer Events, adjusting IMS_BASE and IMS_TENANT. Configure privacy permissions. Prefer a Shopify Web Pixel extension for production app distribution.
4. Confirm checkout order ID normalization and browser/webhook linkage. Where permitted and needed, set `ims_visitor_id` as a merchant-controlled cart/order attribute before checkout; do not write identities without consent. The current pixel provides a late order observation fallback, not a guaranteed cross-device or accelerated-checkout bridge.
5. Place a development-store order and capture actual webhook payloads. The API ignores Shopify orders flagged `test`; use trusted synthetic fixtures/local tests for test orders, or an explicitly isolated test tenant with approved test-mode handling. Never change production filtering just to make a test order appear as sales.
6. Configure the supplied `integrations.shopify_sync` for historical/rolling reconciliation. It requires SHOPIFY_API_VERSION and SHOPIFY_ADMIN_ACCESS_TOKEN; execute `python3 -m integrations.shopify_sync --tenant CLIENT_ID --since 2026-01-01T00:00:00Z`. Validate live permissions/financial policy. Privacy/deletion webhook orchestration and merchant-specific checkout integration remain additional implementation.

## Spend import and automation

UTM convention: `utm_source=google&utm_medium=cpc&utm_campaign={campaignid}` for Google; `utm_source=meta&utm_medium=paid_social&utm_campaign={{campaign.id}}` for Meta; stable campaign key for Simpli.fi. Existing naming conventions require an explicit mapping table before import. Auto-tagging can identify Google source, but absent campaign UTM does not create campaign-ID linkage.

```bash
python3 -m integrations.spend_sync google --start 2026-10-01 --end 2026-10-31 --out /private/jobs/google.csv
python3 -m ims.cli import-spend CLIENT_ID /private/jobs/google.csv
python3 -m integrations.spend_sync meta --start 2026-10-01 --end 2026-10-31 --out /private/jobs/meta.csv
python3 -m ims.cli import-spend CLIENT_ID /private/jobs/meta.csv
```

Google environment: GOOGLE_ADS_API_VERSION, GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_DEVELOPER_TOKEN, optional GOOGLE_ADS_LOGIN_CUSTOMER_ID, plus either GOOGLE_ADS_ACCESS_TOKEN or all GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET / GOOGLE_ADS_REFRESH_TOKEN. Use a supported API version at installation. Meta: META_API_VERSION, META_AD_ACCOUNT_ID, META_ACCESS_TOKEN with appropriate permissions. Tokens must never appear in logs. These API jobs have mocked contract tests, not live vendor validation. Implement alerting/retry for rate limits and expired permissions; an error must not be treated as zero spend.

Simpli.fi: map an approved report export to `examples/spend.csv` and import via the same CLI. Native report API/scheduling depends on account access and is not implemented. Re-import overlapping 7-day windows to capture vendor spend restatements. Upserts replace rows, not add duplicate cost; a vendor that omits previously reported zeroed rows needs an explicit complete-window reconciliation routine.

Suggested timers (run from project root with virtualenv and secure environment configured):

- Every minute, single runner lock: `python3 -m integrations.deliver_conversions`.
- Hourly: spend fetch then import per client/account; alert on failure and preserve previous good data.
- Hourly after import: full rolling-window export to a separate table per client/model.
- Nightly: database backup via SQLite online backup API, encrypted off-host copy, health/freshness checks.
- Nightly: supplied Shopify reconciliation/backfill job; registered experiment outcome ingest as configured. Native non-IP outcome adapters remain additional integration work.

The supervised runner is `python3 -m integrations.run_pipeline --config /etc/ims/pipeline.json`. See examples/pipeline.json and deploy/ims-pipeline.service/.timer. The runner records success/failure and skips later jobs for a tenant after a failure. Configure real alerting on failed runs. The example service expects database/job writable paths under /var/lib/ims; align any Cloud SDK credential/cache directory with the service sandbox. Protect env files and grant only the service user access. The platform-neutral CSV adapter and signing contract are in ALL-PLATFORMS.md.

Back up with `python3 -m ims.cli backup /absolute/private/backups/unique-name.sqlite3`; it uses the SQLite online backup API and integrity check with mode-600 output. Encrypt backups at rest/off-host and test restoration. Issue a replacement key using `python3 -m ims.cli issue-key CLIENT_ID --role client --label reporting-rotation`, verify it, then revoke old fingerprint. Never rotate an in-use key without updating its consumers.

Never use concurrent outbox runners; there is no multi-worker lease in v1. Use `flock` or a single systemd service. Dead-letter items require operator investigation; do not blindly replay stale conversion timestamps beyond vendor windows.

## Pricing

```bash
python3 -m ims.cli markup CLIENT_ID --effective 2026-11-01 --basis-points 10000
```

10000 basis points means 100% markup. Use `--channel meta` for a channel override. A new effective date versions the pricing; changing an existing effective date restates history and is audited. No raw spend is exposed to client credentials or the standard export.

## BigQuery and Looker Studio

Create separate dataset per client. Keep a private administrative dataset separate; do not copy vendor cost into client datasets. The job identity needs dataset write permissions and query-job permissions; the report identity needs only safe dataset read/query permissions. Do not grant client access at the whole agency project level.

```bash
python3 -m integrations.export_bigquery --tenant CLIENT_ID --start 2026-01-01 --end 2026-12-31 --model last_touch --table project-id:client_safe.attribution_last_touch
```

Exporter replaces the WHOLE target table with the requested snapshot. It supports up to 367 days; use deliberate full-window snapshots, not a one-day export that accidentally erases history. Historical partitioned incremental publication is further development. Use separate target table per model.

In Looker Studio, add BigQuery native connector to the client's safe table. Recommended fields: date/channel/campaign filters, spend, net revenue, attributed orders, ROAS, CPA, CPC, CPM, CTR, and data freshness. Ratios must use SUM(revenue)/SUM(media_cost), SUM(media_cost)/SUM(orders), etc.; do not average row metrics. Only use client-safe data even for owner-credential reports. A client-facing experiment page should publish reviewed aggregates from the agency analysis, not arbitrary query parameters or raw unit records.

## Go-live and rollback

Keep existing tracking active in a carefully configured comparison period without double-counting optimization conversions. Reconcile order-level totals for 7–14 days, evaluate consent coverage and unattributed share, and validate native conversion acceptance. Test client isolation, markup and raw-cost export exclusion using real permissions. Cut over one destination at a time; retain prior settings for rollback. Disable the new destination tags and scheduler if discrepancies occur. Keep verified merchant orders as the reconciliation source.
