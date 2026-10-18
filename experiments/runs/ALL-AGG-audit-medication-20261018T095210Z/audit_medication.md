# Medication audit — ALL-AGG-audit-medication-20261018T095210Z

- results_sha256: `29148c8eeba8f0dfbb1f58825a1611dbe21087c2fbbc5f927f211ab001e3ac91`
- git: `88cdeac1140d6cb1717657aef5434aab22534fde` (dirty: False)
- dictionary sha256 `7a948a61c924c36f143546621beb86b3ca6028fda534d3fb364ee45bd1c53319`; pharma `1df4ff0568cf71d11a1e8d5d3e2ce43e3dfbec63e1ae1780a14d7659e6a99f86`
- treated_patients.csv sha256 `2016d3e3025b66081889e4fe64c3359c280f2be79534b57fb82e31db4050c5ef`

## Coverage

- entries: {"total": 4653, "by_column_status": {"csii_basal:PARSED": 1085, "csii_basal:PARSED_WITH_WARNING": 4, "csii_bolus:NON_TARGET_MEDICATION": 1, "csii_bolus:PARSED": 535, "csii_bolus:PARSED_WITH_WARNING": 19, "insulin_iv:NON_MEDICATION": 1, "insulin_iv:PARSED_WITH_WARNING": 9, "insulin_sc:PARSED": 828, "oral_agents:NON_TARGET_MEDICATION": 1783, "oral_agents:PARSED": 321, "oral_agents:PARSED_WITH_WARNING": 67}, "unrecognised_or_ambiguous": 0}
- rates: {"insulin_sc_entries_parsed_to_drug_and_dose": [828, 828], "oral_entries_parsed_to_drug_and_dose": [2171, 2171], "target_administration_parse_rate": 1.0, "target_dose_known_rate": 1.0, "sulfonylurea_formulation_basis": {"DICTIONARY": 44, "DOSE_RULE": 169, "INFERRED": 67}, "target_events_on_cgm_timestamp_rate": 0.9993}

## Treated population

{"by_partition": {"T": {"patients": 30, "treated": 22, "insulin": 20, "sulfonylurea": 4, "glinide": 0, "insulin_and_secretagogue": 2}, "E": {"patients": 70, "treated": 50, "insulin": 39, "sulfonylurea": 10, "glinide": 3, "insulin_and_secretagogue": 2}, "ALL": {"patients": 100, "treated": 72, "insulin": 59, "sulfonylurea": 14, "glinide": 3, "insulin_and_secretagogue": 4}}, "differs_from_legacy": [{"patient_id": "2078", "partition": "E", "legacy": true, "production": false}], "definition": ">= 1 parsed administration of insulin (any route; CSII basal rate > 0 counts), a sulfonylurea or a glinide (Table 5.1)"}

## Day coverage / CSII / i.v.

- day coverage: {"recordings": 79, "target_admin_q1_median": [0.929, 1.0], "target_admin_min": 0.2143, "below_0_8": 4, "any_administration_median_blueprint_style": [1.0]}
- CSII: {"basal_entries": 1087, "bolus_entries": 554, "recordings": 34, "recordings_pump_entries_end_before_record_end": 21, "suspend_entries": 2, "zero_boluses": 23, "zero_rate_entries": 4, "basal_entry_interval_min_q0_q50_q100": [15.0, 240.0, 825.0]}
- i.v. column: {"administration:insulin": 9, "iv_fluid:electrolyte": 9, "iv_fluid:iv_fluid": 6, "iv_fluid:iv_glucose": 3, "non_medication_text:None": 1}
- i.v. glucose: {"events": 3, "patients": 2, "in_T": 0, "in_E": 3, "volume_and_concentration_known": 3, "rate_or_duration_known": 0, "co_administered_with_iv_insulin": 3, "with_cgm_below_70_within_2h": 0}

## G3: PASS

- G3.1-parse-rate: PASS (1.0)
- G3.2-day-coverage: PASS (1.0)
- G3.3-timing-resolution: PASS (15)
- G3.4-treated-E-with-variation: PASS (50)

## G2 re-check: PASS

- {"E_treated_L1": [154, 154], "E_treated_with_L1": [30, 30], "E_treated_m_w": [9.23, 9.23], "E_treated_patients": [51, 50]}

## Representation QA (TUNING only)

```
{
 "scope": "TUNING partition, treated recordings, label-eligible times",
 "readings": 23651,
 "seconds_per_1000_readings": 0.32,
 "features": {
  "act_basal": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.73,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.625,
    1.25
   ]
  },
  "act_glinide": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 1.0,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    0.0
   ]
  },
  "act_insulin_total": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.2121,
   "p1_p50_p99_max": [
    0.0,
    0.395,
    3.136,
    4.376
   ]
  },
  "act_intermediate": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.6959,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    1.538,
    1.712
   ]
  },
  "act_prandial": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.5933,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    2.876,
    3.972
   ]
  },
  "act_su": {
   "n": 23651,
   "nan_share": 0.0456,
   "zero_share": 0.78,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.754,
    0.787
   ]
  },
  "csii_active": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.7901,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    1.0,
    1.0
   ]
  },
  "csii_rate_iu_h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.7901,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.9,
    0.9
   ]
  },
  "glinide_dose_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 1.0,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    0.0
   ]
  },
  "glinide_last_dose": {
   "n": 23651,
   "nan_share": 1.0,
   "zero_share": null,
   "p1_p50_p99_max": null
  },
  "glinide_min_since_last": {
   "n": 23651,
   "nan_share": 1.0,
   "zero_share": null,
   "p1_p50_p99_max": null
  },
  "glinide_n_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 1.0,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    0.0
   ]
  },
  "glinide_p30": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 1.0,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    0.0
   ]
  },
  "glinide_p60": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 1.0,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    0.0
   ]
  },
  "insulin_basal_dose_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.7314,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    15.0,
    30.0
   ]
  },
  "insulin_basal_last_dose": {
   "n": 23651,
   "nan_share": 0.7288,
   "zero_share": 0.0,
   "p1_p50_p99_max": [
    4.0,
    6.0,
    16.0,
    16.0
   ]
  },
  "insulin_basal_min_since_last": {
   "n": 23651,
   "nan_share": 0.7288,
   "zero_share": 0.0111,
   "p1_p50_p99_max": [
    0.0,
    690.0,
    1425.0,
    1440.0
   ]
  },
  "insulin_basal_n_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.7314,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    1.0,
    2.0
   ]
  },
  "insulin_bolus_dose_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.38,
   "p1_p50_p99_max": [
    0.0,
    10.0,
    42.0,
    70.0
   ]
  },
  "insulin_bolus_last_dose": {
   "n": 23651,
   "nan_share": 0.3795,
   "zero_share": 0.0,
   "p1_p50_p99_max": [
    3.0,
    7.0,
    28.0,
    28.0
   ]
  },
  "insulin_bolus_min_since_last": {
   "n": 23651,
   "nan_share": 0.3795,
   "zero_share": 0.0245,
   "p1_p50_p99_max": [
    0.0,
    315.0,
    1305.0,
    1440.0
   ]
  },
  "insulin_bolus_n_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.38,
   "p1_p50_p99_max": [
    0.0,
    2.0,
    4.0,
    6.0
   ]
  },
  "insulin_p30": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.2124,
   "p1_p50_p99_max": [
    0.0,
    0.389,
    3.126,
    4.376
   ]
  },
  "insulin_p60": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.2137,
   "p1_p50_p99_max": [
    0.0,
    0.381,
    3.083,
    4.376
   ]
  },
  "iob_insulin": {
   "n": 23651,
   "nan_share": 0.0047,
   "zero_share": 0.2107,
   "p1_p50_p99_max": [
    0.0,
    3.714,
    20.358,
    31.423
   ]
  },
  "iv_insulin_recent": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.9993,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.0,
    1.0
   ]
  },
  "min_since_glinide": {
   "n": 23651,
   "nan_share": 1.0,
   "zero_share": null,
   "p1_p50_p99_max": null
  },
  "min_since_insulin": {
   "n": 23651,
   "nan_share": 0.2128,
   "zero_share": 0.0395,
   "p1_p50_p99_max": [
    0.0,
    240.0,
    1380.0,
    1440.0
   ]
  },
  "min_since_su": {
   "n": 23651,
   "nan_share": 0.75,
   "zero_share": 0.0127,
   "p1_p50_p99_max": [
    0.0,
    600.0,
    1440.0,
    1440.0
   ]
  },
  "su_dose_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.8084,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    60.0,
    90.0
   ]
  },
  "su_last_dose": {
   "n": 23651,
   "nan_share": 0.75,
   "zero_share": 0.0,
   "p1_p50_p99_max": [
    30.0,
    30.0,
    30.0,
    30.0
   ]
  },
  "su_min_since_last": {
   "n": 23651,
   "nan_share": 0.75,
   "zero_share": 0.0127,
   "p1_p50_p99_max": [
    0.0,
    600.0,
    1440.0,
    1440.0
   ]
  },
  "su_n_24h": {
   "n": 23651,
   "nan_share": 0.0,
   "zero_share": 0.8084,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    2.0,
    3.0
   ]
  },
  "su_p30": {
   "n": 23651,
   "nan_share": 0.0456,
   "zero_share": 0.7798,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.754,
    0.787
   ]
  },
  "su_p60": {
   "n": 23651,
   "nan_share": 0.0456,
   "zero_share": 0.7799,
   "p1_p50_p99_max": [
    0.0,
    0.0,
    0.754,
    0.787
   ]
  }
 },
 "within_recording_sd_q50": {
  "act_insulin_total": [
   0.529
  ],
  "act_su": [
   0.095
  ]
 },
 "recordings_with_varying_insulin_activity": 22,
 "act_insulin_total_abs_step_q50_q99": [
  0.007,
  0.524
 ],
 "spearman": {
  "act_insulin_total~iob_insulin": 0.763,
  "act_insulin_total~insulin_bolus_min_since_last": -0.723,
  "act_insulin_total~insulin_bolus_dose_24h": 0.8,
  "act_su~su_min_since_last": -0.685,
  "insulin_p60~act_insulin_total": 0.974
 }
}
```

