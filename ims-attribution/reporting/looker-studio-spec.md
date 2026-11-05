# Client reporting specification

Use native BigQuery connection to a dedicated client-safe dataset. Reports may be shared with view-only client access; never use raw agency tables as hidden data sources. Owner credentials must point only at safe dataset. Report download and exploration must remain safe even if a viewer inspects all available fields. Require model and currency filters; compare models without summing them.

## Page 1 — Executive performance

Controls: date, channel, campaign; one attribution model per data source/table. Cards: billable media cost, net merchandise revenue, attributed purchase count, ROAS, CPA. Trend: daily revenue/cost; table: campaign cost/orders/revenue/ROAS/CPA/CTR/CPC/CPM. Show unattributed revenue alongside recorded marketing credit. Annotate revenue policy, timezone and freshness.

Calculated fields for BigQuery row-level data:

| Metric | Formula |
|---|---|
| ROAS | `CASE WHEN SUM(media_cost)>0 THEN SUM(revenue)/SUM(media_cost) ELSE NULL END` |
| CPA | `CASE WHEN SUM(orders)>0 THEN SUM(media_cost)/SUM(orders) ELSE NULL END` |
| CPC | `CASE WHEN SUM(clicks)>0 THEN SUM(media_cost)/SUM(clicks) ELSE NULL END` |
| CPM | `CASE WHEN SUM(impressions)>0 THEN 1000*SUM(media_cost)/SUM(impressions) ELSE NULL END` |
| CTR | `CASE WHEN SUM(impressions)>0 THEN SUM(clicks)/SUM(impressions) ELSE NULL END` |

Do not use average of row ROAS/CPA/CPC/CPM. `orders` is purchase-event count (fractional in multi-touch models), not net fulfilled orders. Refunds reduce revenue, not purchase count. `orders_per_click` is not Shopify website conversion rate. Do not compare it to session conversion rate as though the denominators match.

## Page 2 — Attribution comparison

Separate model tables, equal reporting dates, same order population. Compare first-touch, last-touch, linear and position-based credit. Distinguish recorded from inferred behavior. v0.2 does not have data-driven attribution or probabilistic cross-device identity. Unattributed is visible, not redistributed to make a channel look better.

## Page 3 — CTV associations

Dedicated data source from `--kind ctv`. Cards: associated verified orders/revenue, billable CTV cost, associated ROAS/CPA. Label EVERY association chart as household/network IP view-through association. The supplied CTV export is a whole-window campaign snapshot: use its start_date/end_date as labels, not a false daily timeseries. Source quality, matching coverage and window sensitivity appear in supplemental diagnostic/report annotations. A daily CTV aggregate table is a further reporting extension.

Never add CTV-associated sales to click-attributed sales. Show 24-hour/7-day/30-day windows separately; do not sum their overlapping counts. Client output contains no IP or network key.

## Page 4 — Incremental lift

Only analyst-approved registered experiments. Show preregistered hypothesis, unit, dates, treatment/control counts, control exclusion enforcement evidence, net-revenue policy, revenue per unit, lift interval, permutation p value, sample-ratio checks, and iROAS on billable incremental cost. Label provisional results and underpowered tests clearly. No claim that a matched-IP purchase is an incremental purchase.

The engine calculates results and the agency publication API/UI approves completed experiments. The supplied Community Connector reads only those approved safe aggregates; no raw units, salt or IP keys enter its schema. The installer deploys that connector and assembles this chart layout in the client's Looker account. A live report cannot be published into an account without that access.

## Page 5 — Data health

Last successful source sync, newest order/spend date, consent capture coverage, unattributed share, skipped/error/dead-letter counts, and merchant ledger reconciliation status. `/api/status` provides safe job/outbox timestamps and counts. It is not yet automatically a BigQuery data-health table; configure a safe status export or operator panel.

## Agency workspace

Separate access and separate data source. Add vendor cost, billable cost, gross profit, pricing rule effective dates, account mapping, connector capabilities, signed delivery failures, reconciliation and experiment diagnostics. No agency sheet, connection or credential may appear in the client report configuration.
