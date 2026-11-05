# Installation candidate 1.0

Initial deployment scope: Google Ads, Meta, Simpli.fi, Shopify ecommerce, CTV household association, registered incremental measurement and Looker Studio output. Extensible canonical connectors remain available for future platforms.

## Work completed since developer release 0.2

- Importable server GTM HTTP client and ledger-forwarding templates generated from original sandbox source.
- Self-contained Shopify customer-events pixel with server GTM HTTP route; no dynamic SDK download required.
- Consent-gated, per-order Simpli.fi image/script conversion-tag adapter using the actual account-issued URL.
- Native Google Ads click-upload and Meta CAPI senders, stable event IDs, per-destination states, bounded retries and missing-identifier/expiry handling. Alternative sGTM native-tag route retained.
- Simpli.fi scheduled file/HTTPS report ingestion for spend and approved CTV/network data; no invented vendor API endpoints.
- Completed analyst-approval/publication boundary for client-facing incremental results; net-outcome reconciliation unpublishes affected reports.
- Looker Studio Community Connector for attribution, CTV and approved incremental results, with client-role enforcement and safe-field projection.
- Configuration generator producing database, credentials, Compose services, scheduler, secrets files, tenant installers and GTM settings; non-destructive preflight.
- Container scheduler, per-job due intervals, supervised dependency failure handling, rotating online backups.
- Signed Shopify privacy webhook handling, merchant data-request queue and local customer/store data operations.
- Optional WooCommerce reference plugin/read-only API sync and BigCommerce paid-order API reference. BigCommerce refund allocation and merchant-specific commerce edge cases remain gated, not silently treated as supported net revenue.

## What “complete” means here

The scoped software and installation assets above are supplied. This is not proof of a live production deployment. Actual account authorization, supported vendor settings, GTM Preview, checkout tests, native destination diagnostics, CTV exports/control capabilities and Looker account deployment require the operator's accounts. A provider that withholds viewer-level CTV data cannot be made to export it by IMS code.

Docker is not available on the authoring host, so the final image build/container rollout has not been executed here. PHP is not available here; the optional WooCommerce plugin has no claimed PHP runtime test. GTM and Apps Script tests use local API mocks, followed by explicit live acceptance steps. Treat this as an install-and-validate candidate, not an assurance of zero defects or zero additional work for every merchant.

Direct Google click uploads are subject to current API/action eligibility. Google documents access restrictions for some developer tokens; verify eligibility and use the supported server GTM website-tag route when necessary: https://developers.google.com/google-ads/api/docs/conversions/upload-offline

No commitment is made that implementation fits a particular hour count. Ask the installer to quote the explicit steps in INSTALL-FIRST.md and flag any observed code defect separately, rather than re-quoting the broader optional feature roadmap.
