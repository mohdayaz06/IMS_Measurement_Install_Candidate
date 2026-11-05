# Local validation

Run date: 4 November 2026. Synthetic data only; no merchant/ad-account credentials used.

Commands:

```
python3 -m unittest discover -s tests -v
node --test tests/pixel.test.cjs tests/assets.test.cjs
python3 examples/demo.py
```

Result: **56 Python tests and 14 JavaScript tests passed (70 total)** for installation candidate 1.0. Python syntax, JSON configuration, documentation links and inline console JavaScript also passed. Demo shows 100% markup changing $1,000 vendor cost to $2,000 client-facing cost and $6,000 revenue yielding 3.0 client ROAS.

Coverage includes attribution conservation across four models, order/refund/spend deduplication, post-order and expired touch exclusion, direct-channel rules, refunds before orders, money denominators, effective pricing, tenant isolation, forbidden client mutations, invalid credentials, Shopify HMAC/replay validation, denied consent, CTV impression dedup/windowing, HMAC tenant separation, no raw IP persistence, known-network exclusions, and CTV control outcomes counted without requiring impressions. Added checks cover arbitrary-platform signed ingestion, capability authorization, expired/tampered/conflicting deliveries, campaign/account namespaces, CSV fragment aggregation, Shopify authoritative snapshot/refund restatement, trusted consent blocks, backup restoration, key issuance, pipeline failure handling and real loopback HTTP serving.

Added release coverage: installation bundle generation, native Google upload partial-failure/identifier requirements, Meta provider acknowledgement/event ID, destination send deduplication, Simpli.fi file ingestion/browser-tag gating, signed Shopify privacy handling, completed-experiment publication, due-interval scheduling, import-template JSON and mocked server GTM execution, self-contained Shopify installer syntax, Looker agency-token rejection and safe-field projection.

Google/Meta API responses, GTM APIs and Apps Script APIs are mocked. Setup ownership syscall is mocked because this authoring host cannot chown to deployment UID 10001. Docker/PHP runtimes are unavailable here. GTM Preview, Shopify live checkout, native platform receipt, image build, real-load behavior and deployed reporting permissions remain installation acceptance work. Passing local tests is not evidence of incrementality in a real campaign.
