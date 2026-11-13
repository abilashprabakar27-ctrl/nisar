# Graph Report - nisar-change-explorer  (2026-11-13)

## Corpus Check
- Corpus is ~14,122 words - fits in a single context window. You may not need a graph.

## Summary
- 273 nodes · 584 edges · 11 communities (8 shown, 3 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 11 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 9

## God Nodes (most connected - your core abstractions)
1. `read_window()` - 23 edges
2. `run()` - 19 edges
3. `scene()` - 18 edges
4. `assess_availability()` - 16 edges
5. `detect_change()` - 15 edges
6. `make_file()` - 15 edges
7. `PassRef` - 11 edges
8. `validate_result()` - 11 edges
9. `validate()` - 10 edges
10. `availability()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `availability()` --calls--> `assess_availability()`  [EXTRACTED]
  api/app.py → workers/check.py
- `refs()` --calls--> `PassRef`  [EXTRACTED]
  tests/test_floods.py → api/schemas.py
- `assess_availability()` --uses--> `PassRef`  [INFERRED]
  workers/check.py → api/schemas.py
- `lowest_quality()` --uses--> `PassRef`  [INFERRED]
  workers/check.py → api/schemas.py
- `test_analysis_flow_and_cache()` --calls--> `validate_result()`  [EXTRACTED]
  tests/test_api.py → api/schemas.py

## Import Cycles
- None detected.

## Communities (11 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (36): bbox_for(), expected_slices(), make_file(), test_bbox_outside_raises(), test_cache_hit_does_not_reread(), test_http_range_reads_fetch_a_fraction_of_the_file(), do_GET(), do_HEAD() (+28 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (20): cache_dir(), load(), make_key(), save(), _event(), _new(), _run(), run_analysis() (+12 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (17): gb(), load(), main(), cmr_granules(), download(), load_aois(), main(), match() (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (17): analysis_agreement(), analysis_events(), analysis_result(), AnalyzeIn, availability(), AvailabilityIn, BBoxIn, catalog_file() (+9 more)

### Community 4 - "Community 4"
Cohesion: 0.14
Nodes (20): ChangeResult, _classify(), _db(), detect_change(), _drop_small(), _hv_ok(), _lee(), _median() (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.22
Nodes (23): validate_result(), bright_scene(), hv_scene(), refs(), run(), scene(), test_degenerate_no_change_falls_back(), test_flood_recovered_by_otsu_not_fixed_threshold() (+15 more)

### Community 6 - "Community 6"
Cohesion: 0.22
Nodes (12): PassRef, P(), test_gap_straddle_warns(), test_lowest_quality_reported(), test_masked_insufficient(), test_mixed_beta_warns(), test_mixed_geometry_insufficient(), test_mixed_quality_limits_line() (+4 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (10): build, depends_on, env_file, environment, ports, REDIS_URL, image, services (+2 more)

## Knowledge Gaps
- **1 isolated node(s):** `nisar-change-explorer`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 79 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `read_window()` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **What connects `nisar-change-explorer` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06440677966101695 - nodes in this community are weakly interconnected._
- **Why does `assess_availability()` connect `Community 6` to `Community 3`, `Community 4`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.06914893617021277 - nodes in this community are weakly interconnected._
- **Why does `validate_result()` connect `Community 5` to `Community 1`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.08902439024390243 - nodes in this community are weakly interconnected._