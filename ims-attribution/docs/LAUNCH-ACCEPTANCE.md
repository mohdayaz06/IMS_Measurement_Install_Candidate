# Installed acceptance checklist — Google, Meta, Simpli.fi

Record the operator, tenant, date and evidence links. None of these live results is claimed by the local test suite.

| Check | Expected evidence |
|---|---|
| Application/TLS | API health/ready returns version 1.0; valid certificate; persistent data survives restart |
| Access | Invalid tokens denied; client cannot call agency operations or see vendor costs; no secrets in source/page/network logs |
| Markup | $1,000 vendor spend +100% = $2,000 client cost; $6,000 revenue yields 3 ROAS; CPA/CPC/CPM use client cost |
| Shopify paid order | Signed order creates one ledger entry; refresh/retry doesn't duplicate |
| Refund/edit | Net subtotal matches Shopify; old included refund not subtracted twice; current snapshot visible |
| Consent | Denied analytics creates no identity; denied marketing blocks new destination sends; trusted withdrawal stops pending deliveries |
| Checkout link | Normal, accelerated and mobile checkout tested; unlinked purchases remain reported as unattributed |
| Server GTM | Imported template compiles in Preview; allowed origin accepted; other origins/key rejected; ledger tag fires once |
| Google spend | Daily cost/impressions/clicks and campaign IDs reconcile to report; timezone/currency match |
| Google conversion | Correct website tag OR eligible import action receives value/currency/order ID; same primary action not fired twice |
| Google API eligibility | If direct upload selected, current developer-token and action eligibility confirmed; otherwise use supported server GTM website tag route |
| Meta spend | Account daily report totals reconcile; correct campaign-key mapping |
| Meta CAPI | Test Events/diagnostics show accepted event, stable event_id, matching fields and correct value; test code removed before live |
| Simpli.fi spend | Real scheduled CSV mapped correctly; stale/missing feed creates failure, not zero cost |
| Simpli.fi conversion | Actual account-issued tag tested; platform confirms receipt/definition; no claim that SDK onload is attribution |
| CTV association | Actual served impression/viewer-IP source confirmed; no server/proxy IP; matching permissions and coverage documented |
| CTV counting | One order at most once in chosen CTV window; click/CTV overlap not summed; cost channel/campaign agrees |
| Incrementality | Pre-registration, independent unit population and actual control suppression demonstrated; both arms' purchases captured |
| Experiment publication | Only completed analyst-approved report visible to client; no raw units/salts/IP keys; net corrections require review |
| Looker | Connector rejects agency token; safe fields only; ratios recomputed from sums; model/window/currency clear |
| Job health | Deliberate credential/feed failure visible in job status; subsequent dependent work skipped; recovery tested |
| Backup | Restore an online backup into a separate instance and verify row totals/auth; encrypted off-host copy configured |
| Native delivery errors | Missing IDs, expired events and vendor errors visible, not counted as accepted conversions |
| Cutover | Existing sender/settings recorded; one primary route per action; rollback disables new routing without deleting merchant ledger |

Use a small agreed pilot budget after acceptance. A synthetic test that shows positive lift is a test of arithmetic, not proof a real campaign is incremental.
