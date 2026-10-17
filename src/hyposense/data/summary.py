"""Loader for Shanghai_T2DM_Summary.xlsx (static clinical record, ONE ROW PER RECORDING).

The summary is keyed by recording ("Patient Number" = recording key, e.g. 2001_0_20201102), not
by patient. A patient with several recordings has several rows, which may differ. Values are
kept raw (object). Typed parsing of static context happens in the feature stage.

The field "Hypoglycemia (yes/no)" is loaded only so that its presence can be audited. It is
listed in FORBIDDEN_FEATURE_COLUMNS and must never become a label or feature (Blueprint N2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hyposense.data.columns import SchemaError, normalise_header

# normalised raw header -> canonical name (all 33 columns of figshare v5)
SUMMARY_COLUMNS: dict[str, str] = {
    "Patient Number": "recording_key",
    "Gender (Female=1, Male=2)": "sex_code",
    "Age (years)": "age_y",
    "Height (m)": "height_m",
    "Weight (kg)": "weight_kg",
    "BMI (kg/m2)": "bmi",
    "Smoking History (pack year)": "smoking_pack_years",
    "Alcohol Drinking History (drinker/non-drinker)": "alcohol",
    "Type of Diabetes": "diabetes_type",
    "Duration of diabetes (years)": "duration_y",
    "Acute Diabetic Complications": "acute_complications",
    "Diabetic Macrovascular Complications": "macrovascular_complications",
    "Diabetic Microvascular Complications": "microvascular_complications",
    "Comorbidities": "comorbidities",
    "Hypoglycemic Agents": "prescribed_hypoglycemic_agents",
    "Other Agents": "other_agents",
    "Fasting Plasma Glucose (mg/dl)": "fpg_mgdl",
    "2-hour Postprandial Plasma Glucose (mg/dl)": "ppg2h_mgdl",
    "Fasting C-peptide (nmol/L)": "c_peptide_fasting_nmol_l",
    "2-hour Postprandial C-peptide (nmol/L)": "c_peptide_2h_nmol_l",
    "Fasting Insulin (pmol/L)": "insulin_fasting_pmol_l",
    "2-hour Postprandial insulin (pmol/L)": "insulin_2h_pmol_l",
    "HbA1c (mmol/mol)": "hba1c_mmol_mol",
    "Glycated Albumin (%)": "glycated_albumin_pct",
    "Total Cholesterol (mmol/L)": "total_cholesterol_mmol_l",
    "Triglyceride (mmol/L)": "triglyceride_mmol_l",
    "High-Density Lipoprotein Cholesterol (mmol/L)": "hdl_mmol_l",
    "Low-Density Lipoprotein Cholesterol (mmol/L)": "ldl_mmol_l",
    "Creatinine (umol/L)": "creatinine_umol_l",
    "Estimated Glomerular Filtration Rate (ml/min/1.73m2)": "egfr",
    "Uric Acid (mmol/L)": "uric_acid_mmol_l",
    "Blood Urea Nitrogen (mmol/L)": "bun_mmol_l",
    "Hypoglycemia (yes/no)": "summary_hypoglycemia_flag",
}
FORBIDDEN_FEATURE_COLUMNS = frozenset({"summary_hypoglycemia_flag"})


@dataclass(frozen=True)
class SummaryTable:
    frame: pd.DataFrame  # index: recording_key; columns: canonical names; raw values
    raw_headers: tuple[str, ...]


def load_summary(path: Path) -> SummaryTable:
    raw = pd.read_excel(path, dtype=object, header=0)
    headers = tuple(str(h) for h in raw.columns)
    norm = {h: normalise_header(h) for h in headers}
    unknown = [h for h, n in norm.items() if n not in SUMMARY_COLUMNS]
    missing = sorted(set(SUMMARY_COLUMNS) - set(norm.values()))
    if unknown or missing:
        raise SchemaError(f"summary schema mismatch: unknown={unknown} missing={missing}")
    df = raw.rename(columns={h: SUMMARY_COLUMNS[n] for h, n in norm.items()})
    keys = df["recording_key"].astype(str).str.strip()
    if keys.duplicated().any():
        raise SchemaError(f"duplicate recording keys in summary: {sorted(keys[keys.duplicated()])}")
    df = df.assign(recording_key=keys).set_index("recording_key").sort_index()
    return SummaryTable(frame=df, raw_headers=headers)
