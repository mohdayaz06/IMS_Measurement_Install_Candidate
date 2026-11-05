# All-platform support: exact scope and connector contract

The attribution engine has no list limiting it to Google, Meta or Simpli.fi. Any platform can appear as a channel when traffic has consistent campaign tagging and merchant purchases can be independently captured. Full native automation and event-level impression measurement depend on each platform's interfaces and contractual access.

## Capability matrix

| Platform/interface | Independent merchant conversion association | Automatic spend | Send conversions back | CTV IP impression joining |
|---|---|---|---|---|
| Google Ads | Tagged landing + verified orders | Fetcher supplied; live auth/QA needed | Through configured sGTM tag; live QA needed | Only if approved usable viewer-level logs exist; not supplied |
| Meta | Tagged landing + verified orders | Fetcher supplied; live auth/QA needed | Through configured sGTM CAPI tag; live QA needed | Same log/access condition; not assumed |
| Simpli.fi | Tagged landing + verified orders | Canonical CSV/signed adapter; native account API work needed | Actual approved account interface required | Core matcher supplied; viewer-log access and audience-control dependency |
| Microsoft, TikTok, Pinterest, Snapchat, LinkedIn, Amazon, other DSPs | Same generic attribution contract | Signed canonical adapter/CSV; native API plugins to be added | Provider-specific server endpoint or sGTM template to be added | Only if provider supplies appropriate logs and permissions |
| Affiliate, email, direct publisher/sponsorship | UTMs + verified merchant order | Approved spend/export normalization | Vendor-specific if supported/needed | Only for actual video impression records with usable network signals |
| Platform with no usable APIs/exports | Tagged traffic and merchant order association may still work | Manual canonical import | Cannot promise automated delivery | Cannot independently reconstruct missing impression/IP data |

No platform is claimed to have a tested native adapter simply because generic ingestion supports its name. Measurement compatibility, native vendor optimization delivery, spend sync and incrementality execution are separate checkboxes.

## Connector registration

Agency POST `/api/connectors`:

```json
{"id":"my-dsp-ctv","platform":"my_dsp","channel":"ctv","account":"account123","currency":"USD","timezone":"America/New_York","capabilities":["spend","ctv_impressions"]}
```

Response gives `/ingest/TENANT/CONNECTOR`, a server secret-environment-variable name and campaign prefix. Set a new random >=32-character signing secret in that variable and in the trusted source adapter. Secrets are not in the database, browser, client dataset or source archive. The API container and any local API test runner must receive the same server secret environment. Native ad-platform API tokens are separate from this IMS signing secret.

`platform` identifies the vendor; `channel` identifies the reporting media class. For CTV through any DSP set `channel:"ctv"` so CTV cost matches the separate association report. For display/search/social choose a consistent agreed channel. The provider ID remains in impression metadata; full per-provider cost reporting would require an additional report dimension. Register a separate connector per account/media class as needed.

## Signed ingestion

Headers: X-IMS-Timestamp (Unix seconds), X-IMS-Delivery (unique ID), X-IMS-Signature (hex HMAC-SHA256). Signed bytes: `timestamp + '.' + delivery + '.' + exact_raw_body`. Allowed clock skew is five minutes. Delivery reuse with different body is rejected. Identical repeat is acknowledged as duplicate. The delivery ID is not the conversion/order ID; canonical row IDs provide independent retry safety.

Body: `{"type":"spend","rows":[...]}`. Types: spend, orders, refunds, touches, ctv_impressions, order_networks. Connector can only send its registered capabilities. Do not grant an ad-platform connector permission to create merchant revenue; only trusted merchant-order adapters receive orders/refunds capability. All ad platforms share ONE verified merchant order ledger.

A batch contains 1–1,000 rows and max 1 MiB. Canonical writes are idempotent; a mid-batch failure can leave earlier rows applied, so retry the complete batch. This is at-least-once processing, not a distributed exactly-once guarantee.

Campaign keys are normalized to `platform:account:campaignID`. Use this same string as utm_campaign in the universal-connector mode. For example `utm_source=my_dsp&utm_medium=paid&utm_campaign=my_dsp:account123:campaign456`. For click channels `utm_source` must equal the registered channel (or normalize to it). Google/Meta source aliases are normalized; arbitrary custom platform aliases need consistent naming or a mapping adapter. Native fetchers support unprefixed IDs by default; the scheduler's campaign_prefix option switches them to the same namespaced convention. Never mix both conventions for the same historical account without a controlled migration.

## CSV integration

Use `integrations/universal_csv.py` with `examples/vendor-spend-mapping.json`. Mapping declares source column names, constants and a cost multiplier (for example micros-to-major-unit conversion). It aggregates ad-set fragments by date/campaign/currency before signing and uploading canonical campaign totals. Accepts ordinary decimal, ISO date inputs; vendor-specific date/localized number formats need normalization upstream. Does not execute arbitrary mapping expressions.

```
python3 -m integrations.universal_csv --csv /private/vendor.csv --mapping /etc/ims/vendor-map.json --endpoint https://tracking.example.com/ingest/CLIENT_ID/CONNECTOR_ID
```

Set IMS_INGEST_SECRET securely for this CLI. Schedule the vendor export/download using approved account methods. No scrape of an authenticated vendor UI is supplied. Stable UTC event timestamps, account reporting timezone and currency are mandatory. Missing spend is unknown, not zero.

## Acceptance per added platform

Provide one redacted vendor cost export, one tagged landing/verified test order, interface documentation and access scope. Demonstrate repeat import safety, campaign-key match, correct markup, no cross-client data, correct timezone/currency, and fresh data in Looker. If destination forwarding is required, show platform acceptance and duplicate controls. If CTV is required, demonstrate actual impression semantics, viewer-IP quality and permission; if incrementality is required, demonstrate treatment/control execution and complete independent outcomes.
