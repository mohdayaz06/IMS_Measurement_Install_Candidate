# CTV household association and incrementality

## What this release adds

`ims/ctv.py` implements exact public-IP association between trusted CTV impression logs and independently verified merchant orders. It stores only per-tenant keyed HMAC network identifiers, not raw IP addresses. These remain pseudonymous personal/network data, not anonymous data. Set a randomly generated, server-only `IMS_IP_HMAC_KEY` (32+ characters) before ingestion. Keep it in a secrets manager. Rotating it breaks previous matching unless a versioned transition is implemented.

CTV reports are separate from click attribution. One verified order receives at most one CTV association, to its last eligible logged impression within the requested window. The client report exposes aggregate campaign association counts/revenue only. It applies existing markup rules to `channel=ctv` spend. Associated ROAS/CPA are not incremental ROAS/CPA. Never sum CTV-associated sales with click-attributed sales: they can describe the same order.

## Required upstream data

1. DSP/ad-server verified impression log: unique served impression ID, actual viewer IP (or a mutually compatible approved network key), timestamp, campaign ID and provider. An auction request, available placement, bid, stream request or SSAI server IP is not proof an ad was served to that household. Require event-level evidence and eligibility/consent rights.
2. Trusted merchant-side conversion IP collected at purchase, with verified order ID, timestamp and permissions. Do not use a tracking server's own IP, Cloudflare proxy IP, arbitrary X-Forwarded-For, or a browser-supplied address. Validate the trusted proxy chain and original client IP extraction server-side. Shopify `browser_ip` availability/merchant authorization must be confirmed; this is not automatically enabled in the supplied Shopify webhook handler.
3. Permission to process and join these signals for the intended measurement purpose and a defined retention/deletion policy. Consent, opt-out, sale/share restrictions and data-use agreements must be reflected in both sources. HMAC does not remove these requirements. Implementation must propagate opt-out/erasure and apply retention to network keys as well as raw logs.

**Simpli.fi dependency:** its public materials describe household/cross-device attribution, but do not establish that your account can export row-level viewer IP impression logs or enable externally controlled randomized household suppression. Confirm those capabilities in writing before promising independent IMS IP-level measurement. If IP logs are withheld, masked or keyed incompatibly, independent exact-IP joining cannot be recreated from aggregate vendor reports. Alternatives are approved clean-room/provider joins, authorized household identifiers, vendor-reported association shown as such, or randomized geo incrementality.

## API

Agency-only POST `/api/ctv/impressions`:

```json
{"rows":[{"impression_id":"dsp-unique-id","ts":"2026-10-09T12:00:00Z","campaign":"CTV123","provider":"approved-dsp","ip_address":"ACTUAL_PUBLIC_VIEWER_IP","measurement_permitted":true,"network_type":"residential"}]}
```

Agency-only POST `/api/ctv/order-networks`, after the verified order already exists:

```json
{"rows":[{"order_id":"123","ip_address":"ACTUAL_PURCHASE_IP","measurement_permitted":true,"network_type":"residential"}]}
```

Raw values exist transiently during processing, never in database fields/audit records. Ensure reverse proxies, error monitoring and upstream logs do not retain these request bodies. The API does not magically prove the caller's permission assertion; upstream enforcement is required. Known VPN/proxy/datacenter/shared/SSAI-server labels are rejected; automatic network-quality classification is not implemented. Unknown network type is accepted and counted as a quality flag, not asserted residential.

Client/agency GET `/api/ctv/report?start=2026-10-01&end=2026-10-31&window_hours=168` returns associated counts/revenue and billable cost metrics. Defaults to 7 days; allowed 1–720 hours. This is a configurable business choice, not a causal threshold. Compare 24-hour, 7-day and 30-day sensitivity before choosing the reporting policy. Counts include verified orders without matching IP in denominator, so missing measurement remains visible.

Exact-IP code normalizes IPv4-mapped IPv6 but does not arbitrarily group IPv6 /64 addresses. Dynamic IP, mobile networks, carrier NAT, apartment/business/shared Wi-Fi, VPNs, IPv6 address rotation and SSAI can cause false matches or missed matches. IP match is a network-level association, not proof of a unique household/person or attention to an ad.

## Real incremental lift

Register a `household_ip` experiment through the existing experiment endpoint. Enroll the ENTIRE eligible network population before the experiment starts via agency POST `/api/ctv/experiments/ID/enroll` with `ip_address`, `measurement_permitted:true` and quality classification. The API returns stable pseudonymous unit and randomized arm. Feed actual control suppression and treatment inclusion to the DSP using an approved, securely handled audience mapping. The software does not deliver that suppression itself, and HMAC tokens alone cannot be targeted unless the DSP supports the agreed key.

Record merchant purchase IPs for ALL eligible orders, including control households that never receive a CTV impression. Then POST `/api/ctv/experiments/ID/sync-outcomes` to link verified orders to BOTH arms. It intentionally does not require an impression match when counting control outcomes. All pre-enrolled units remain in the denominator, including zero purchases. Use `/api/experiments/ID/results` for ITT lift, confidence interval and permutation p value; supply incrementally incurred billable cost for client iROAS.

IP instability and unequal capture between arms can bias this estimate. If IP-defined randomization cannot remain stable, use an approved stable household identifier or preregistered randomized geo clusters. Do not compare exposed IPs against arbitrary unexposed website visitors and call the difference causal. Advertiser-selected eligible networks and sufficient outcome coverage are required; collecting impressions from treatment only cannot reconstruct a valid control universe.

## Additional developer quote items

- Confirm/export DSP impression and eligible-audience/control data, validate SSAI viewer-IP semantics, dedup log IDs and reject invalid traffic.
- Trusted original-IP collection at conversion, consent/opt-out propagation, versioned HMAC keys, retention/erasure, network-quality filtering and monitored match coverage.
- Actual DSP suppression, contamination checks and independently captured control outcomes; document IMS experiment process and power plan.
- Configure safe CTV aggregate BigQuery export/Looker tab, overlap analysis with click-attributed order ledger and window sensitivity reporting. The supplied exporter supports `--kind ctv --window-hours 168`; publish to a dedicated CTV table. It replaces the selected whole-window campaign snapshot and never exports IP/network keys. Do not merge this table's associated sales into click-attribution totals.

## Primary references

- Microsoft household attribution and dynamic-IP limits: https://learn.microsoft.com/en-us/xandr/monetize/household-attribution-faq
- Microsoft network-level cross-device association: https://learn.microsoft.com/en-us/xandr/monetize/household-attribution
- Simpli.fi household/cross-device capabilities (not a log-export guarantee): https://simpli.fi/latest/simpli-fi-launches-incrementality-focused-cross-device-attribution-built-for-multi-location-brands
- IAB CTV data/permissions context: https://www.iab.com/wp-content/uploads/2023/03/IAB-Project-Crosswalk-2.0-Connected-TV-Compliance-in-a-New-Privacy-Law-Era.pdf
