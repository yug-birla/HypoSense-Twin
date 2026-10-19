# Honesty card

What HypoSense Twin **does** and **does not** show, in one page.

| Claim | Status |
|---|---|
| The system runs end to end: data → twin → forecast → policy → interface | **Shown** (tests, browser E2E, live demo) |
| Features never use future information | **Shown** (bitwise truncation equality; future-perturbation test) |
| Replay and decisions are deterministic | **Shown** (identical decision-log hashes) |
| The model warns earlier than a simple trend rule on development data | **Development evidence only** (M1 − M0 +23.1 points, CI 9.4 to 43.7). A post-hoc CGM-level rule matches the learned models on T |
| Medication exposure improves warning (H1: M3 > M2) | **Not shown.** Development Δ +3.6 points, CI includes 0. The confirmatory test on sealed data has **not been run** |
| Clinical benefit, safety or accuracy in practice | **Not claimed** |
| Accuracy on newly uploaded patients | **Not claimed.** The development model is applied, with no evaluation on those data |

Where the data come from:
- ShanghaiT2DM (public, CC BY 4.0).
- Lows are **CGM-detected**; capillary glucose often disagrees around 70 mg/dL.

What can go wrong:
- **False alerts happen.** The guided demo's first real alert was one, and it is shown as such.
- **Missed lows happen.**
- No forecast is given when data are insufficient. This is by design, and it is never shown as
  low risk.

What we never do:
- recommend doses or treatment;
- call a patient "safe";
- present a development result as confirmatory;
- open the sealed evaluation data before the protocol freeze.

Pending human gates:
- clinical-pharmacist review of the medication kernels;
- owner approval of the confirmatory operational definitions (P-C11).

The protocol freeze and the confirmatory evaluation follow those gates.
