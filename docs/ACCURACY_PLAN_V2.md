# Accuracy plan v2

Where we are (see docs/accuracy_log.md): IoU 0.68, precision 0.88, recall 0.74 against OPERA on the Tonle Sap window; 0.55 / 0.58 / 0.91 on the neighbouring window. The only reference is OPERA (another model), on about half the window. No independent accuracy number exists.

Goal: a result we can defend. Two things move that: (1) independent evidence that does not come from OPERA or from us, (2) a better method judged on it.

## Rules (unchanged, plus two)
1. OPERA and any other map is a second opinion. Tune on one part, report on parts never used for tuning.
2. Every experiment is logged, failures included. Weak numbers are reported.
3. NEW: labels must be made blind to our result. The labeller never sees our map, `ours`, or the strata file.
4. NEW: AI-assisted labels are disclosed as such and are not human ground truth. A person spot-checks a share of them and the check agreement is reported.

## Independent evidence we can get without a login
| Source | What it gives | Independence |
|---|---|---|
| Sentinel-2 L2A (AWS Earth Search STAC, open COGs) | Clear-sky optical scenes; water by MNDWI (green vs SWIR) with the scene's own cloud mask | Different sensor, wavelength and method from NISAR and from OPERA-S1 |
| Fable vision labels on Sentinel-2 chips | Water / not water / unsure at about 90 blind, stratified points per area | Independent of our map; AI-assisted, disclosed |
| Human spot-check of 20 labels | Agreement rate between Fable and a person | The honesty check on the AI labels |
| NISAR passes already local (Tonle Sap 11, Nile Sudd 11) | Temporal evaluation: every pass vs the nearest clear S2 scene | Same data, more tests |

## Stages
| Stage | Work | Output | Who |
|---|---|---|---|
| A1 | Fetch Sentinel-2 scenes for Tonle Sap window and neighbour, Kanpur, Morigaon: clearest scene nearest the before and after dates, MNDWI water map, cloud mask | `backend/scripts/fetch_s2_reference.py`, reference rasters in git-ignored data | agent |
| A2 | Score our new water against the S2 optical change (water-after minus water-before), same west/east/neighbour split | rows in `docs/accuracy_log.md` | agent |
| A3 | Blind check points: make a stratified sample, render Sentinel-2 chips, Fable labels them without seeing our result, second Fable pass for consistency, score precision/recall with Wilson 95% intervals; user labels 20 as the human check | `docs/ACCURACY_LABELLED.md` | Fable agents |
| B | Method v5 judged on A1 to A3: more passes per side, HV wet-field filter for the neighbour, incidence-angle normalisation, per-site-type thresholds. Tune west only, accept only if east and neighbour hold | `change.py`, tests, log | agent |
| C | Leftovers: cap High confidence when new water is tiny or recall unknown; drivers endpoint with rain; align deck, abstract and form answers with the app's real numbers; resource list gaps | code, docs | agent |
| D | Review and freeze: Fable red-team of the evaluation (leakage, circularity), final table, full tests, PR | `docs/ACCURACY_FINAL.md` | Fable review |

## Left out or weak right now (this plan fixes)
- No independent accuracy number (A1 to A3).
- South neighbour over-predicts water, precision 0.58 (B).
- Kanpur shows High confidence on 68 ha with no recall measure (C).
- Morigaon and Nile Sudd have no reference (A1 gives Morigaon one; Nile Sudd stays unvalidated unless OPERA tiles are supplied).
- Deck, abstract and form answers quote the older science pipeline's IoU 0.72, not the app's numbers (C).
- Official challenge page resource list never fetched (needs a browser; user step).
- Drivers (rain) exist in our science code but are not served by the team backend (C).

## Human steps
- Spot-check 20 of the AI labels (about 15 minutes).
- Paste the challenge page's resource list into `docs/RESOURCES.md`.
- Revoke the Earthdata token (still pending).
