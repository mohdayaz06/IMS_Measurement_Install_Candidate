# Install-first release — Google, Meta and Simpli.fi

This is the installation path for the agreed initial stack. Shopify is the primary ecommerce setup. The shared ingestion framework remains available for future ad platforms. Do not commission new platform adapters unless you choose to extend this scope.

## Files to give the installer

The whole ZIP. Start with this file, examples/install.json, dist/, and docs/LAUNCH-ACCEPTANCE.md. HANDOFF.md describes architecture; earlier release briefs are background, not a requirement to build an enterprise SaaS before this pilot.

## Preparation

1. Select an IMS-owned Linux host with durable disk. Install Docker Compose and Caddy, or use equivalent managed hosting/TLS. Create Google server GTM containers using the supported Google provisioning workflow. This package does not provision paid cloud resources or sign into merchant accounts.
2. Obtain Shopify merchant app access and webhook secret, Google Ads reporting OAuth/developer-token access, Meta reporting/CAPI token, and the actual Simpli.fi scheduled report/conversion-tag details. Use supported API versions. Store secrets in the install shell environment or approved secrets manager.
3. Copy examples/install.json outside source control. Set domains, tenant ID, Shopify domain and per-client account variable mappings. Confirm currency/timezone. Include needed environment names in copy_environment. Add host-to-container feed_mounts if scheduled Simpli.fi CSVs will arrive in a host directory.
4. Choose ONE purchase route per destination: sGTM native tags OR direct native sender. The example defaults to sGTM forwarding; native examples are disabled. Do not enable both against the same primary action. A Simpli.fi vendor-issued browser tag can be set under simplifi.browser_tag as `{ "type":"image", "url":"https://i.simpli.fi/ACTUAL_ACCOUNT_ENDPOINT" }` or an approved external script URL. Do not use the example text as a real URL. Use only vendor-confirmed value/order/currency parameters; placeholders are {{value}}, {{order_id}}, {{currency}}.

## Generate and deploy

From the unpacked source directory:

```
python3 build_assets.py
python3 -m unittest discover -s tests -q
node --test tests/pixel.test.cjs tests/assets.test.cjs
python3 -m ims.setup --config /private/install.json --output /private/ims-deployment
python3 -m ims.preflight /private/ims-deployment
```

Generation creates a real per-installation database, private credentials, environment file, Docker Compose JSON, job configuration, storefront installers and GTM settings. Use a fresh empty output directory. Root generation applies container ownership UID 10001; unprivileged generation uses the current UID. Run on ordinary Linux with filesystem ownership support. The local test host does not support that chown operation; the generation test mocks that syscall. Do not bypass production ownership errors.

```
cd /private/ims-deployment
docker compose -f compose.json up --build -d
```

Use the generated Caddyfile on the host and point tracking-domain DNS to it. Keep the API bound to loopback behind TLS. Configure WAF/rate limits/admin network access in your hosting environment. Mount approved feed directories read-only into jobs (feed_mounts in configuration). API and jobs share the durable SQLite database; do not enable multiple API instances or multiple competing job runners. Backups rotate locally; add encrypted off-host backup using your hosting tools.

## GTM imports (configuration, not source coding)

In each client's server GTM container:

1. Templates → New → Import `dist/ims-http-client.tpl` as a Client template and `dist/ims-ledger-forwarder.tpl` as a Tag template.
2. Create the client and enter values from generated installers/TENANT/sgtm-settings.json. Set the exact allowed storefront origins. Keep gatewayKey private on the server.
3. Create the ledger-forwarder tag with generated endpoint/bridgeKey. Tighten its HTTP permission to the exact IMS API host. Trigger only custom event `ims_touch`.
4. If sgtm_purchase_forwarding is enabled, configure supported Google Ads purchase and Meta CAPI tags on `purchase`. Use your account action/pixel IDs and secrets, event_id, transaction_id, value, currency and matching IDs from event data. Use the supplied server gateway rather than browser-supplied purchase values as the source of verified purchases. Importing a template does not connect a Google/Meta account automatically.
5. Test browser OPTIONS/POST, origin denial, marketing-denied purchase routing and a verified order in GTM Preview. Publish only after these pass.

The imported GTM template structures and JavaScript are locally tested with API mocks; Google GTM Preview is the live-runtime acceptance step. No GTM account was available to publish/test here.

## Shopify install

Paste generated installers/TENANT/shopify-pixel.js into Customer Events as JavaScript only. The SDK is bundled; no custom programming/dynamic library load is required. Set appropriate analytics/marketing permissions and verify Shopify sandbox origin behavior for the merchant. Subscribe orders/paid, refunds/create, customers/data_request, customers/redact and shop/redact to `https://API_DOMAIN/shopify/TENANT` using the merchant app secret. Configure the supplied GraphQL sync job for rolling reconciliation and historical backfill.

The pixel observes order identity and browser marketing permission. Signed paid-order data creates revenue. If an accelerated checkout or blocked browser prevents identity linkage, the verified purchase remains visible as unattributed rather than being invented or dropped. Measure that coverage in the acceptance run. A custom merchant Web Pixel app is optional further distribution work, not required to execute this supplied custom-pixel route.

## Simpli.fi install

Use scheduled authorized reports, actual account pixel/tag, and column mapping. Feed adapters handle spend, CTV impressions and trusted purchase-network records. For CTV spend use channel=ctv and the same campaign key as impressions. Do not configure a fictional API URL. Confirm viewer-IP impression logs and measurement permission with Simpli.fi before enabling independent IP joining. Aggregate campaign reports cannot replace those records.

The SDK invokes the configured Simpli.fi browser image/script tag only on observed checkout with marketing permission and browser/order duplicate suppression. A loaded request is not a platform acceptance/attribution claim. Independent IMS revenue still comes from verified merchant orders. Disable duplicated legacy senders at cutover. If Simpli.fi supplies a supported server conversion receiver, use the signed generic receiver adapter with that confirmed interface.

## Looker Studio install

The generated looker-connector directory contains Code.js and appsscript.json. Paste into an Apps Script project (show manifest file in project settings), deploy as a Community Connector, then add it as a data source in Looker Studio. The generated URL whitelist matches your API origin. Authenticate using CLIENT token from the private credentials file. Agency credentials are explicitly refused. Create separate data sources for attribution, CTV association and approved experiments.

Use reporting/looker-studio-spec.md for the chart layout and calculated ratios. Existing BigQuery export is also available if preferred. A native Looker report cannot be published into your account from this offline package; assembling the supplied layout and setting sharing are installation tasks. No new paid attribution subscription is needed for the connector path. Google/Apps Script quotas and hosting usage still apply.

## Incrementality operation

Register/enroll control and treatment units before campaign start. Enforce actual control exclusions in buying platforms. Capture purchases for both arms independently; zero-outcome enrolled units stay in denominators. Use the supplied analysis and approved-publication workflow. Only completed analyst-approved results become visible in client reports. IP outcome reconciliation handles later net-revenue changes and unpublishes affected results for review.

## Honest completion boundary

Supplied: runnable application, install generator, GTM import files, bundled Shopify pixel, scheduled jobs, Google/Meta reporting and optional native conversion senders, Simpli.fi file/tag adapters, client reporting connector, approved experiment publication, privacy operations and local tests.

Still account-dependent: credentials/API eligibility, DNS/cloud setup, GTM native tag settings/Preview, merchant checkout/order comparison, Simpli.fi data rights and exports, actual campaign holdout execution, Looker deployment/sharing and real-load acceptance. These cannot be completed or certified without those accounts. Optional BigCommerce/WooCommerce reference adapters are separate from the primary Shopify installation; inspect their refund-policy limits before enabling them.
