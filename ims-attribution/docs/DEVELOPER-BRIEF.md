# Installer quote brief — Google, Meta and Simpli.fi

Please quote installing and validating the supplied IMS Measurement 1.0 candidate. Do not quote the older optional enterprise product roadmap as required work for this launch. Start with INSTALL-FIRST.md.

## Supplied assets

Application/database, install generator, private credential provisioning, API/jobs Compose services, rotating backups, GTM import templates and tenant settings, bundled Shopify pixel, merchant reconciliation, Google/Meta spend and optional native conversion jobs, Simpli.fi scheduled-report/tag adapters, client-safe Looker connector, attribution/CTV/experiment logic, approval/publication UI/API and local tests.

## Installation work to quote

1. Review code/tests and run generated deployment on one IMS-owned durable Linux host.
2. Configure DNS/TLS, persistent disk, secret values, WAF/admin access, off-host backups and restart/restore checks.
3. Import GTM templates, enter generated settings and merchant Google/Meta native tag configuration where that route is selected. Test in Preview and publish after approval.
4. Install generated Shopify pixel, subscribe signed webhook topics, authorize GraphQL sync and validate merchant orders/refunds/checkout linkage.
5. Connect Google/Meta account reporting and one conversion route per action. Configure Simpli.fi's actual authorized scheduled report/tag interface. Mount feed directory if used.
6. Deploy Apps Script Community Connector and create Looker data sources/chart layout with client-only credentials.
7. Execute LAUNCH-ACCEPTANCE.md, document account-dependent blockers and cutover/rollback.

## Dependencies to confirm before a fixed quote

Existing hosting/DNS access; supported API access/tokens; Shopify merchant permissions; Simpli.fi report/tag details; CTV viewer-level data and control suppression availability if independent IP incrementality is included. If the provider does not expose the necessary CTV data, mark that capability blocked by data access rather than promising engineering will recreate it.

## Quote boundaries

Separate installation/configuration, live validation and any specific code defects discovered. Identify a defect by file/behavior and proposed correction before adding development hours. New platforms, commerce adapters beyond the primary Shopify installation, distributed HA, staff SSO and additional analytics products are optional extensions.

The authoring host could not run Docker/PHP or access live ad/merchant/GTM/Looker accounts, so acceptance must include a real image build and connected tests. The source package is not a guarantee that no defect will be found. Do not assume an earlier hour estimate is a fixed completion promise.

IMS owns source, infrastructure, credentials and data. List recurring hosting/licensing costs separately. No new paid attribution SaaS subscription is required for the supplied measurement/connector route.
