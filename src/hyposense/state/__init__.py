"""Patient State Engine (the twin): PatientState with CGMState (+ causal episode tracker),
MedicationExposureState (S3 engines), DataQualityState, ForecastState and OutcomeLedger;
deterministic, timestamp-ordered update(). Blueprint 9.1-9.2, 25.2. Implemented in S4
(docs/ARCHITECTURE.md §4.4).
"""
