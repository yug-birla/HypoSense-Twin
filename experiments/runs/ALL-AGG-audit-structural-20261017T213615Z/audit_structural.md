# Structural audit — ALL-AGG-audit-structural-20261017T213615Z

- results_sha256: `09e780bdfd5ada0d360a45a3da6dbee0ccf483dc483921a3e92dc64fcc568cd3`
- git: `f68f98a12349d4ba26e35155abdf12ea5b867074` (dirty: False)
- manifest files_sha256: `5f9d65b4e9233d4ecdd05438e80bb94314290cd5e2d9fdd21e353487cd3cc4ab`
- archive: figshare v5 sha256 `59b5f5c4053a32bb6b7827844a0191597dc82228fe88ce332a189fdfc659c4cb`
- access scope: aggregate_audit (aggregate-only)

## Dataset

| Measure | Value |
|---|---|
| Recording files / recordings / patients | 109 / 109 / 100 |
| Recordings per patient | {'1': 92, '2': 7, '3': 1} |
| Rows / rows without CGM | 112475 / 13 {'2029_0_20210526': 13} |
| CGM readings | 112462 |
| Monitored (patient-)days | 1170.626 |
| Recording days min/median/max | [2.562, 12.677, 13.938] |

## Timestamps and CGM

| Measure | Value |
|---|---|
| Timestamp parse rate | 1.0 |
| Intervals (n) / ≤20 min share / exactly-15 share | 112353 / 0.999902 / 0.999902 |
| Interval histogram (min) | {'b:14-16': 112342, 'd:(20,30]': 7, 'e:(30,60]': 3, 'f:>60': 1} |
| Gaps >30 / >60 min; max gap | 4 / 1; 212.0 min |
| CGM parse rate | 1.0 |
| CGM min/p1/median/p99/max | [39.6, 57.6, 129.6, 298.8, 468.0] |
| ≤40 mg/dL (floor) / out of [20,600] | 329 / 0 |
| Values on the 1.8 mg/dL grid (0.1 mmol/L origin) | 1.0 |
| Quality flags | {'floor': 329, 'gap_before': 11, 'rapid_change': 9, 'warmup': 872} |

## Medication and meals (structural)

- columns: {'insulin_sc': {'entries': 828, 'entries_with_amount_unit': 828, 'recordings_with': 54}, 'oral_agents': {'entries': 2171, 'entries_with_amount_unit': 2171, 'recordings_with': 92}, 'insulin_iv': {'entries': 10, 'entries_with_amount_unit': 9, 'recordings_with': 6}, 'csii_bolus': {'entries': 555, 'recordings_with': 35, 'text_cells': 1}, 'csii_basal': {'entries': 1089, 'recordings_with': 34, 'text_cells': 2}}
- entries with amount+unit: {'insulin_sc': 1.0, 'oral_agents': 1.0, 'insulin_iv': 0.9}
- vocabulary sizes: {'insulin_sc': 13, 'oral_agents': 15, 'insulin_iv': 7}
- administration alignment: {'entries': 4653, 'on_cgm_row_rate': 0.999355, 'at_cgm_timestamp_rate': 0.999355}
- meals: {'both_languages': 3805, 'diet_cn_entries': 3805, 'diet_en_entries': 3808, 'diet_en_not_available': 745, 'diet_on_cgm_row': 3807, 'recordings_with_diet': 109}

## Issues

{'info:empty_row': 10, 'info:unitless_header': 10, 'warning:nominal_start_mismatch': 3, 'warning:sheet_name_mismatch': 1, 'warning:timestamp_subsecond': 13, 'warning:value_unparseable': 3}

## Blueprint reconciliation

| Metric | Blueprint | Measured (v5) | Status |
|---|---|---|---|
| recordings | 109 | 109 | MATCH |
| patients | 100 | 100 | MATCH |
| n_header_variants | 5 | 5 | MATCH |
| cgm_rows | 112287 | 112462 | EXPECTED DIFFERENCE |
| monitor_days | 1168.8 | 1170.7 | EXPECTED DIFFERENCE |
| days_per_recording | [2.56, 12.68, 13.94] | [2.56, 12.68, 13.94] | MATCH |
| interval_hist | {'<=16': 112168, '16-30': 7, '30-60': 3} | {'16-30': 7, '30-60': 3, '<=16': 112342, '>60': 1} | EXPECTED DIFFERENCE |
| readings_le40 | 329 | 329 | MATCH |
| min_cgm | 39.6 | 39.6 | MATCH |
| ins_sc_entries | 827 | 828 | EXPECTED DIFFERENCE |
| recs_ins_sc | 54 | 54 | MATCH |
| oral_entries | 2166 | 2171 | EXPECTED DIFFERENCE |
| recs_oral | 92 | 92 | MATCH |
| recs_csii | 35 | 35 | MATCH |
| recs_iv | 6 | 6 | MATCH |
| diet_entries | 3802 | 3808 | EXPECTED DIFFERENCE |
| diet_not_available | 742 | 745 | EXPECTED DIFFERENCE |
| cbg_values | 3262 | 3269 | EXPECTED DIFFERENCE |
| recs_with_cbg | 94 | 94 | MATCH |
