# Release 0.2 changes

Adds a consolidated developer handoff; explicit all-platform capability matrix; signed connector registration/ingestion with least-capability scopes, secret references, replay protection and campaign/account namespaces; vendor-neutral CSV column mapping and fragment aggregation; supervised multi-tenant job pipeline and sample systemd schedule; safe operational status; key issuance and backup commands; trusted consent withdrawal; Shopify GraphQL backfill/reconciliation with current net snapshots; date-bounded attribution queries; CTV console panel; client-role hiding of agency pricing controls; complete client report/formula specification; synthetic runnable web demo; expanded automated tests.

Existing 0.1 order/cost tables are preserved. New tables/views are created idempotently at startup. No sample production database or secrets are included. Back up any existing pilot database before using this release. In-flight experimental databases from development snapshots containing a different connectors schema are unsupported; fresh staging databases or an explicit reviewed migration are required. Legacy pixel archive remains a reference only.

51 local checks pass (47 Python + 4 SDK). Live Shopify/GTM/DSP integrations, production load, deployed report IAM and all vendor-specific native APIs remain acceptance work, not inferred from test success.
