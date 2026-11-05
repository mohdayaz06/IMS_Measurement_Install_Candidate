# API contracts

All POST bodies JSON, max 1 MiB. UTC timestamps require offset. Order/customer/event identifiers max 160 chars `[A-Za-z0-9_.:-]`. Monetary API inputs use decimal major units (USD dollars); storage uses integer cents. Bearer keys are tenant scoped, stored as SHA256 hashes, and never sent in query strings. API returns generic input errors to avoid leaking payloads.

| Endpoint | Authorization | Purpose |
|---|---|---|
| GET /health | Public | Liveness/version |
| GET /pixel.js | Public | Collection SDK |
| POST /collect/TENANT | Origin allowlist + CMP consent | Browser touch and optional order observation; untrusted telemetry |
| POST /bridge/TENANT | X-IMS-Bridge-Key | sGTM forwarded touch |
| POST /shopify/TENANT | Shopify HMAC + shop domain | orders/paid and refunds/create |
| GET /api/report?start=YYYY-MM-DD&end=YYYY-MM-DD&model=last_touch | Client or agency | Tenant-scoped report; agency-only extra fields |
| GET /api/customers | Client or agency | Aggregate observed customer summary |
| POST /api/orders | Agency | Trusted canonical order rows |
| POST /api/refunds | Agency | Trusted canonical refund rows |
| POST /api/spend | Agency | Atomic daily campaign spend upsert |
| POST /api/markup | Agency | Effective channel pricing |
| GET /api/audit | Agency | Last 100 audit records |
| GET /api/status | Client or agency | Safe freshness/job delivery status |
| POST /api/deliveries/retry | Agency | Reset eligible failed/test delivery, preserving stable event ID |
| GET /api/experiments/published | Client or agency | Approved safe incremental-measurement snapshots |
| POST /api/experiments/ID/publish | Agency | Require analyst approval and verified holdout enforcement |
| POST /api/experiments/ID/unpublish | Agency | Remove reviewed result from client reporting |
| GET /api/privacy/requests | Agency | Signed merchant privacy request/fulfillment queue |
| POST /api/connectors | Agency | Register platform/account/media capability contract |
| GET /api/connectors | Agency | List configured connectors without secrets |
| POST /ingest/TENANT/CONNECTOR | Per-connector HMAC | Platform-independent canonical batches; see ALL-PLATFORMS.md |
| POST /api/privacy/withdraw | Agency/trusted merchant integration | Withdraw visitor marketing/analytics permission |
| POST /api/privacy/fresh-grant | Agency/trusted merchant integration | Record independently verified fresh consent |
| POST /api/experiments | Agency | Preregister experiment |
| POST /api/experiments/ID/enroll | Agency | Assign unit before start |
| POST /api/experiments/ID/outcomes | Agency | Idempotent observed purchase outcome |
| GET /api/experiments/ID/results | Agency | Fixed-horizon analysis |

Touch: `{"event_id":"UUID","visitor_id":"UUID","ts":"2026-11-04T12:00:00Z","source":"google","medium":"cpc","campaign":"12345","analytics_consent":true,"marketing_consent":false}`. Optional `order_id` links identity, never revenue. Optional `signals` contains consented gclid, gbraid, wbraid, fbp and fbc only. Do not send email, phone or freeform URL/customer data.

Orders import: `{"rows":[{"order_id":"123","visitor_id":"UUID","ts":"2026-11-04T12:01:00Z","currency":"USD","revenue":"199.95","customer_id":"merchant-pseudonym"}]}`. visitor_id/customer_id optional; lack of visitor means unattributed until a valid observation links it.

Refund import: `{"rows":[{"refund_id":"r123","order_id":"123","ts":"2026-11-05T00:00:00Z","amount":"25.00"}]}`.

Spend import: `{"rows":[{"date":"2026-11-04","channel":"google_ads","campaign":"12345","currency":"USD","cost":"1000.00","impressions":100000,"clicks":1000}]}`. Must aggregate per date/channel/campaign before ingest; input rows are canonical totals, not multiple ad-set fragments.

Markup: `{"channel":"*","effective":"2026-11-01","basis_points":10000}`. Client cannot read or write this endpoint.

Experiment registration: `{"id":"holiday-holdout","start":"FUTURE_ISO_TIMESTAMP","end":"LATER_ISO_TIMESTAMP","unit_type":"customer","treatment_fraction":0.5,"hypothesis":"Advertising increases revenue per eligible customer","min_units_per_arm":100}`. `geo_cluster` also accepted. Minimum 20 independent units per arm is a guard, not sufficient power.

Enrollment: `{"unit":"merchant-pseudonym"}`. Every eligible unit enrolled BEFORE start; returns stable control/treatment arm for actual platform suppression/targeting.

Outcome: `{"outcome_id":"order123","unit":"merchant-pseudonym","ts":"IN_WINDOW_TIMESTAMP","revenue":"100.00"}`. One verified purchase per outcome ID. Revenue should match the prespecified refund horizon; outcome adjustment after import is not yet implemented. Do not silently rewrite conflicting outcomes. No outcome means zero, not exclusion.

Experiment results optional query: `incremental_media_cost=1000.00`; use incrementally incurred billable media cost for client iROAS. Never use total mixed-channel spend without defining which spend was randomized.
