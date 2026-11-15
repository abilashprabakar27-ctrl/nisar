# Story results: Kanpur and Morigaon

Run 2026-11-15 on real NISAR GCOV (study window only, read over HTTPS), method `water-change-v4b-before-margin-persist`. Results are saved under `backend/data/results/<id>` on the machine that ran them (git-ignored). These are measured outputs of the method, not accuracy.

| | Kanpur, Uttar Pradesh | Morigaon, Assam |
|---|---|---|
| Result id | 4aa2651811975e19 | d2e865d94fc5e6d3 |
| Window | bbox 80.25 26.35 80.50 26.60 | bbox 92.15 26.15 92.40 26.40 |
| Track | 77 D (ascending/descending: descending) | 91 D |
| Before passes | 30 Aug, 11 Sep | 20 Jun, 2 Jul |
| After passes | 23 Sep, 5 Oct | 14 Jul, 26 Jul |
| Event date used | 22 Sep (as planned) | 8 Jul (moved from 20 Jul, which straddles the 27 Jul to 10 Aug data gap) |
| Became water | 68 ha | 3,299 ha |
| Receded | 68 ha | 42 ha |
| Permanent water | 3,384 ha | 2,965 ha |
| Confidence (v5 rules) | Medium | Lower (97% of new water on cropland, no OPERA) |
| OPERA check | Tile T44RMQ (1 Oct). Of our 68 ha new water, 58 ha (86%) is water in OPERA on that date. OPERA shows 2,680 ha water in total. | None. No OPERA S1 tile near the last after pass. |
| Run time | 250 s | 279 s |

## Honest reading
- **Kanpur shows almost no net flood in this window.** New water (68 ha) is the same size as receded water (68 ha). The 86% means 86% of those pixels are water in OPERA, new or not. Sentinel-2 marks only 14% of the same pixels as new water (docs/accuracy_log.md), so we cannot say this is new water, and the figure says nothing about how much we missed (Sentinel-2 recall is 0.03). The current rules give Medium for this case, and Medium should not be read as "we mapped the flood well". The OPERA tile is dated 1 Oct, 4 days before the last after pass.
- **Kanpur, all water including permanent:** IoU 0.40 against OPERA (we over-predict permanent water relative to OPERA, 3,349 ha vs 2,680 ha). Not a test of change.
- **Morigaon is unchecked.** 3,299 ha of new water between early July and late July is large and plausible for the Brahmaputra season, but there is no independent check, so the label is Lower under the v5 rules and the place is "not checked". The last after pass (26 Jul) is the day before the data gap.
- **Passes are Provisional quality** and may shift when reprocessed.
- **Not tested:** hand-labelled check points. These are still the only accuracy number that does not depend on OPERA.
