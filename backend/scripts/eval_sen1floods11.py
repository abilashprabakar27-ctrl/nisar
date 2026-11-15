#!/usr/bin/env python3
"""Do SCENE-CALIBRATED water thresholds generalise better than fixed ones?

Data: Sen1Floods11 hand-labelled chips (Sentinel-1 VV/VH in dB, human water
labels, JRC permanent-water layer). C-band, so this tests the RECIPE, not
NISAR L-band thresholds.

Methods (single date, dB < t means water):
  A  one fixed global cut-off per polarisation (chosen on tuning events only)
  B  Otsu per chip / per event (no parameters)
  C  scene calibration with NO hand labels: JRC permanent water pixels are free
     'water' samples, JRC==0 pixels are free 'land' samples in the same scene.
       pct    t = q-th percentile of the JRC-water dB distribution
       delta  t = median(JRC-water dB) + delta
       youden t = dB that best separates the JRC-water and JRC-land samples
     each at scene = event (all chips of the event pooled) or chip level.
     Too few samples -> fall back (chip -> event -> fixed A).
  D  logistic regression on VV, VH, VV-VH trained on tuning events
  O  oracle best fixed cut-off per event (uses labels; reference only)

Protocol: every number (A threshold, q, delta, LR weights) is chosen on the 10
tuning events only (manifest tune = train+valid). Leave-one-event-out (LOEO)
across the tuning events shows variability. `--stage test` reads the sealed
chips (manifest sealed_test: Bolivia + official test chips) exactly once, using
the frozen parameters written by `--stage tune`.

NOTE JRCWaterHand ships as binary 0/1 (no occurrence value), so 'occurrence
>= 90 %' cannot be applied; JRC==1 is the water sample and JRC==0 the land
sample. JRC==0 includes the flood itself, so the land sample is contaminated by
flood water (the water-only methods pct/delta are immune to that).
"""
import argparse
import json
import os
import sys
import numpy as np
import rasterio

DS = "/home/sanjayvasudevan/nasa/team_data/datasets"
HL = DS + "/sen1floods11/data/flood_events/HandLabeled"
LO, HI, STEP = -50.0, 25.0, 0.1
NB = int(round((HI - LO) / STEP))
POLS = ["VV", "VH"]
MIN_EVENT_WATER = 500      # a-priori (not tuned): min JRC-water px for event calibration
MIN_CHIP_WATER = 200       # a-priori: min JRC-water px (and land px) for chip calibration
MIN_LAND = 200
PCTS = [50, 75, 90, 95, 98, 99, 99.5]
DELTAS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]
LR_PER_CHIP = 3000
NBOOT = 1000
rng_global = np.random.default_rng(20261115)


def edge(j):
    return LO + STEP * j


def read_chip(name):
    ev = name.rsplit("_", 1)[0]
    cid = name.rsplit("_", 1)[1]
    def rd(layer):
        with rasterio.open(f"{HL}/{layer}/{ev}_{cid}_{layer}.tif") as r:
            return r.read()
    s1 = rd("S1Hand").astype(np.float32)
    lab = rd("LabelHand")[0]
    jrc = rd("JRCWaterHand")[0]
    return s1[0], s1[1], lab, jrc


def hist(x):
    i = np.clip(((x - LO) / STEP).astype(np.int64), 0, NB - 1)
    return np.bincount(i, minlength=NB)


def cum(h):
    return np.concatenate([[0], np.cumsum(h)])


def otsu_idx(h):
    """threshold edge index maximising between-class variance."""
    h = h.astype(float)
    tot = h.sum()
    if tot <= 0:
        return None
    c = np.arange(NB) + 0.5
    w0 = np.cumsum(h)
    m0 = np.cumsum(h * c)
    mt = m0[-1]
    w1 = tot - w0
    ok = (w0 > 0) & (w1 > 0)
    var = np.zeros(NB)
    var[ok] = (mt * w0[ok] - m0[ok] * tot) ** 2 / (w0[ok] * w1[ok])
    return int(np.argmax(var)) + 1  # water = bins < j


def load_summary(name):
    vv, vh, lab, jrc = read_chip(name)
    out = {"name": name, "event": name.rsplit("_", 1)[0]}
    fin = np.isfinite(vv) & np.isfinite(vh)
    valid = (lab >= 0) & fin
    w = valid & (lab == 1)
    l = valid & (lab == 0)
    jw = fin & (jrc == 1)
    jl = fin & (jrc == 0)
    out["n_valid"] = int(valid.sum())
    out["n_lw"] = int(w.sum())
    out["n_jrc_w"] = int(jw.sum())
    out["n_jrc_l"] = int(jl.sum())
    out["jrc_in_label"] = float((jw & (lab == 1)).sum()) / max(1, int(jw.sum()))
    for p, x in (("VV", vv), ("VH", vh)):
        out["cw_" + p] = cum(hist(x[w]))
        out["cl_" + p] = cum(hist(x[l]))
        out["jw_" + p] = hist(x[jw])
        out["jl_" + p] = hist(x[jl])
        out["ha_" + p] = hist(x[fin])
    # logistic-regression training sample
    idx = np.flatnonzero(valid.ravel())
    k = min(LR_PER_CHIP, idx.size)
    sel = rng_global.choice(idx, k, replace=False) if k else idx
    a = np.clip(vv.ravel()[sel], -50, 20)
    b = np.clip(vh.ravel()[sel], -50, 20)
    out["lr_X"] = np.stack([a, b, a - b], 1).astype(np.float32)
    out["lr_y"] = (lab.ravel()[sel] == 1).astype(np.float32)
    return out


def fit_lr(X, y, lam=1e-3, iters=30):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    n1, n0 = y.sum(), (1 - y).sum()
    sw = np.where(y == 1, 0.5 / max(n1, 1), 0.5 / max(n0, 1)) * len(y)  # balanced
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        z = Z @ w
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = Z.T @ (sw * (p - y)) + lam * np.r_[w[:-1], 0]
        H = (Z * (sw * p * (1 - p))[:, None]).T @ Z + lam * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-6:
            break
    return {"w": w.tolist(), "mu": mu.tolist(), "sd": sd.tolist()}


def lr_counts(name, model):
    vv, vh, lab, _ = read_chip(name)
    fin = np.isfinite(vv) & np.isfinite(vh)
    valid = (lab >= 0) & fin
    a = np.clip(vv[valid], -50, 20)
    b = np.clip(vh[valid], -50, 20)
    X = np.stack([a, b, a - b], 1)
    Z = (X - np.array(model["mu"])) / np.array(model["sd"])
    z = Z @ np.array(model["w"][:-1]) + model["w"][-1]
    pred = z > 0
    t = lab[valid] == 1
    tp = int((pred & t).sum()); fp = int((pred & ~t).sum())
    fn = int((~pred & t).sum()); tn = int((~pred & ~t).sum())
    return np.array([tp, fp, fn, tn])


# ---------------------------------------------------------------- thresholds
def counts_at(c, pol, j):
    cw, cl = c["cw_" + pol], c["cl_" + pol]
    tp = cw[j]; fp = cl[j]
    return np.array([tp, fp, cw[-1] - tp, cl[-1] - fp])


def pooled_hist(chips, key):
    return np.sum([c[key] for c in chips], axis=0)


def thr_from_samples(hw, hl, family, param):
    """edge index from JRC-water hist hw and JRC-land hist hl; None if undefined."""
    nw = hw.sum()
    if nw <= 0:
        return None
    cwh = np.cumsum(hw)
    if family == "pct":
        j = int(np.searchsorted(cwh, nw * param / 100.0)) + 1
    elif family == "delta":
        med = int(np.searchsorted(cwh, nw * 0.5))
        j = med + 1 + int(round(param / STEP))
    elif family == "youden":
        nl = hl.sum()
        if nl <= 0:
            return None
        fw = np.concatenate([[0], cwh]) / nw
        fl = np.concatenate([[0], np.cumsum(hl)]) / nl
        j = int(np.argmax(fw - fl))
    else:
        raise ValueError(family)
    return int(np.clip(j, 1, NB))


def calib_thresholds(chips, pol, family, param, scale, fallback_j):
    """per-chip threshold index + fallback level (0 own, 1 event, 2 fixed)."""
    by_ev = {}
    for i, c in enumerate(chips):
        by_ev.setdefault(c["event"], []).append(i)
    ev_thr = {}
    for ev, ids in by_ev.items():
        hw = pooled_hist([chips[i] for i in ids], "jw_" + pol)
        hl = pooled_hist([chips[i] for i in ids], "jl_" + pol)
        ok = hw.sum() >= MIN_EVENT_WATER and hl.sum() >= MIN_LAND
        ev_thr[ev] = thr_from_samples(hw, hl, family, param) if ok else None
    out = []
    for c in chips:
        j, lvl = None, 2
        if scale == "chip":
            hw, hl = c["jw_" + pol], c["jl_" + pol]
            if hw.sum() >= MIN_CHIP_WATER and hl.sum() >= MIN_LAND:
                j = thr_from_samples(hw, hl, family, param)
                lvl = 0
        if j is None and ev_thr[c["event"]] is not None:
            j, lvl = ev_thr[c["event"]], 1
        if j is None:
            j, lvl = fallback_j, 2
        out.append((j, lvl))
    return out


def counts_for(chips, pol, thr):
    return np.array([counts_at(c, pol, j) for c, (j, _) in zip(chips, thr)])


# ---------------------------------------------------------------- metrics
def metr(cn):
    tp, fp, fn, tn = [float(x) for x in cn]
    iou = tp / max(tp + fp + fn, 1)
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    f1 = 2 * p * r / max(p + r, 1e-12)
    return {"IoU": iou, "P": p, "R": r, "F1": f1}


def ev_ids(chips):
    d = {}
    for i, c in enumerate(chips):
        d.setdefault(c["event"], []).append(i)
    return d


def macro(cn, ids_by_ev, key="IoU"):
    return float(np.mean([metr(cn[ids].sum(0))[key] for ids in ids_by_ev.values()]))


def boot(cn, ids_by_ev, rng):
    """stratified (by event) chip bootstrap -> CIs for pooled and macro metrics."""
    pooled = {k: [] for k in ("IoU", "P", "R", "F1")}
    mac = []
    for _ in range(NBOOT):
        sums = []
        for ids in ids_by_ev.values():
            s = rng.choice(ids, len(ids), replace=True)
            sums.append(cn[s].sum(0))
        tot = np.sum(sums, 0)
        m = metr(tot)
        for k in pooled:
            pooled[k].append(m[k])
        mac.append(np.mean([metr(s)["IoU"] for s in sums]))
    ci = lambda v: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
    return {k: ci(v) for k, v in pooled.items()}, ci(mac)


def best_fixed(chips, pol, ev_subset):
    """edge index maximising mean per-event IoU over the given events."""
    evs = ev_ids(chips)
    ids = [evs[e] for e in ev_subset]
    best, bj = -1, None
    for j in range(1, NB):
        v = np.mean([metr(np.sum([counts_at(chips[i], pol, j) for i in ii], 0))["IoU"] for ii in ids])
        if v > best:
            best, bj = v, j
    return bj


def fast_best_fixed(chips, pol, ev_subset):
    evs = ev_ids(chips)
    best = np.zeros(NB + 1)
    for e in ev_subset:
        cw = np.sum([chips[i]["cw_" + pol] for i in evs[e]], 0)
        cl = np.sum([chips[i]["cl_" + pol] for i in evs[e]], 0)
        tp, fp, fn = cw, cl, cw[-1] - cw
        best += tp / np.maximum(tp + fp + fn, 1)
    best[0] = best[NB] = -1
    return int(np.argmax(best))


FAMS = [("pct", q) for q in PCTS] + [("delta", d) for d in DELTAS] + [("youden", 0)]


def sel_param(chips, pol, family, scale, fallback_j, ev_subset):
    evs = ev_ids(chips)
    sub_chips_idx = [i for e in ev_subset for i in evs[e]]
    sub = [chips[i] for i in sub_chips_idx]
    sub_ev = ev_ids(sub)
    cands = [p for f, p in FAMS if f == family]
    best, bp = -1, None
    for p in cands:
        thr = calib_thresholds(sub, pol, family, p, scale, fallback_j)
        cn = counts_for(sub, pol, thr)
        v = macro(cn, sub_ev)
        if v > best:
            best, bp = v, p
    return bp


def run_tune(chips, events):
    """LOEO over tuning events + final frozen parameters."""
    res = {}     # method -> (n_chips,4) held-out counts
    flags = {}   # method -> per chip fallback level
    frozen = {"A": {}, "C": {}, "LR": None}
    idx_of = {c["name"]: i for i, c in enumerate(chips)}
    n = len(chips)
    for pol in POLS:
        res["A_" + pol] = np.zeros((n, 4), int)
        res["BchipOtsu_" + pol] = np.zeros((n, 4), int)
        res["BeventOtsu_" + pol] = np.zeros((n, 4), int)
        res["Oracle_" + pol] = np.zeros((n, 4), int)
        for fam in ("pct", "delta", "youden"):
            for sc in ("event", "chip"):
                res[f"C{fam}_{sc}_{pol}"] = np.zeros((n, 4), int)
                flags[f"C{fam}_{sc}_{pol}"] = np.zeros(n, int)
    detail = {}
    evs = ev_ids(chips)
    # Otsu + oracle do not depend on folds
    for pol in POLS:
        for ev, ids in evs.items():
            hev = np.sum([chips[i]["ha_" + pol] for i in ids], 0)
            jev = otsu_idx(hev)
            ev_cw = np.sum([chips[i]["cw_" + pol] for i in ids], 0)
            ev_cl = np.sum([chips[i]["cl_" + pol] for i in ids], 0)
            io = (ev_cw / np.maximum(ev_cw + ev_cl + ev_cw[-1] - ev_cw, 1))
            io[0] = io[-1] = -1
            jor = int(np.argmax(io))
            detail[(ev, pol, "oracle_j")] = jor
            detail[(ev, pol, "otsu_ev_j")] = jev
            for i in ids:
                c = chips[i]
                jc = otsu_idx(c["ha_" + pol])
                res["BchipOtsu_" + pol][i] = counts_at(c, pol, jc if jc else jev)
                res["BeventOtsu_" + pol][i] = counts_at(c, pol, jev)
                res["Oracle_" + pol][i] = counts_at(c, pol, jor)
    # LOEO
    for held in events:
        train = [e for e in events if e != held]
        for pol in POLS:
            jA = fast_best_fixed(chips, pol, train)
            detail[(held, pol, "A_j")] = jA
            for i in evs[held]:
                res["A_" + pol][i] = counts_at(chips[i], pol, jA)
            for fam in ("pct", "delta", "youden"):
                for sc in ("event", "chip"):
                    p = sel_param(chips, pol, fam, sc, jA, train)
                    detail[(held, pol, f"p_{fam}_{sc}")] = p
                    sub = [chips[i] for i in evs[held]]
                    thr = calib_thresholds(sub, pol, fam, p, sc, jA)
                    cn = counts_for(sub, pol, thr)
                    for k, i in enumerate(evs[held]):
                        res[f"C{fam}_{sc}_{pol}"][i] = cn[k]
                        flags[f"C{fam}_{sc}_{pol}"][i] = thr[k][1]
                    detail[(held, pol, f"j_{fam}_{sc}")] = [t[0] for t in thr]
        print("  LOEO fold done:", held, flush=True)
    # logistic LOEO
    res["D_LR"] = np.zeros((n, 4), int)
    for held in events:
        tr = [c for c in chips if c["event"] != held]
        m = fit_lr(np.concatenate([c["lr_X"] for c in tr]), np.concatenate([c["lr_y"] for c in tr]))
        for i in evs[held]:
            res["D_LR"][i] = lr_counts(chips[i]["name"], m)
    # frozen parameters from all tuning events
    for pol in POLS:
        jA = fast_best_fixed(chips, pol, events)
        frozen["A"][pol] = jA
        for fam in ("pct", "delta", "youden"):
            for sc in ("event", "chip"):
                frozen["C"][f"{fam}_{sc}_{pol}"] = sel_param(chips, pol, fam, sc, jA, events)
    frozen["LR"] = fit_lr(np.concatenate([c["lr_X"] for c in chips]), np.concatenate([c["lr_y"] for c in chips]))
    return res, flags, detail, frozen


def run_test(chips, frozen):
    n = len(chips)
    res, flags, detail = {}, {}, {}
    evs = ev_ids(chips)
    for pol in POLS:
        jA = frozen["A"][pol]
        res["A_" + pol] = np.array([counts_at(c, pol, jA) for c in chips])
        for k in ("BchipOtsu_", "BeventOtsu_", "Oracle_"):
            res[k + pol] = np.zeros((n, 4), int)
        for ev, ids in evs.items():
            hev = np.sum([chips[i]["ha_" + pol] for i in ids], 0)
            jev = otsu_idx(hev)
            cw = np.sum([chips[i]["cw_" + pol] for i in ids], 0)
            cl = np.sum([chips[i]["cl_" + pol] for i in ids], 0)
            io = cw / np.maximum(cw + cl + cw[-1] - cw, 1)
            io[0] = io[-1] = -1
            jor = int(np.argmax(io))
            detail[(ev, pol, "oracle_j")] = jor
            detail[(ev, pol, "otsu_ev_j")] = jev
            detail[(ev, pol, "A_j")] = jA
            for i in ids:
                jc = otsu_idx(chips[i]["ha_" + pol])
                res["BchipOtsu_" + pol][i] = counts_at(chips[i], pol, jc if jc else jev)
                res["BeventOtsu_" + pol][i] = counts_at(chips[i], pol, jev)
                res["Oracle_" + pol][i] = counts_at(chips[i], pol, jor)
        for fam in ("pct", "delta", "youden"):
            for sc in ("event", "chip"):
                p = frozen["C"][f"{fam}_{sc}_{pol}"]
                thr = calib_thresholds(chips, pol, fam, p, sc, jA)
                res[f"C{fam}_{sc}_{pol}"] = counts_for(chips, pol, thr)
                flags[f"C{fam}_{sc}_{pol}"] = np.array([t[1] for t in thr])
                for ev, ids in evs.items():
                    detail[(ev, pol, f"j_{fam}_{sc}")] = [thr[i][0] for i in ids]
    res["D_LR"] = np.array([lr_counts(c["name"], frozen["LR"]) for c in chips])
    return res, flags, detail


# ---------------------------------------------------------------- reporting
def fmt_ci(v, ci):
    return f"{v:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def report(title, chips, res, flags, detail, out):
    evs = ev_ids(chips)
    rng = np.random.default_rng(7)
    lines = [f"### {title}", ""]
    # pooled table
    lines += ["Pooled over all chips of the held-out events (pixel-pooled), 95% CI by event-stratified chip bootstrap.",
              "", "| Method | IoU | Precision | Recall | F1 | Macro IoU (mean of events) |", "|---|---|---|---|---|---|"]
    summ = {}
    for m in res:
        cn = res[m]
        tot = metr(cn.sum(0))
        ci, mci = boot(cn, evs, rng)
        mac = macro(cn, evs)
        summ[m] = (tot, mac)
        lines.append(f"| {m} | {fmt_ci(tot['IoU'], ci['IoU'])} | {fmt_ci(tot['P'], ci['P'])} | "
                     f"{fmt_ci(tot['R'], ci['R'])} | {fmt_ci(tot['F1'], ci['F1'])} | {fmt_ci(mac, mci)} |")
    lines.append("")
    # per event IoU table (headline methods)
    cols = ["A_VV", "BeventOtsu_VV", "Cpct_event_VV", "Cdelta_event_VV", "Cyouden_event_VV", "Cdelta_chip_VV",
            "A_VH", "BeventOtsu_VH", "Cpct_event_VH", "Cdelta_event_VH", "Cyouden_event_VH", "D_LR", "Oracle_VV", "Oracle_VH"]
    cols = [c for c in cols if c in res]
    lines += ["Per-event IoU (events as held out).", "",
              "| Event | chips | water frac (label) | JRC water px | " + " | ".join(cols) + " |",
              "|---|---|" + "---|" * (len(cols) + 2)]
    for ev, ids in evs.items():
        nv = sum(chips[i]["n_valid"] for i in ids)
        nw = sum(chips[i]["n_lw"] for i in ids)
        nj = sum(chips[i]["n_jrc_w"] for i in ids)
        row = [f"{metr(res[c][ids].sum(0))['IoU']:.3f}" for c in cols]
        lines.append(f"| {ev} | {len(ids)} | {nw / max(nv, 1):.3f} | {nj} | " + " | ".join(row) + " |")
    lines.append("")
    # precision/recall per event for fixed and calibrated
    lines += ["Per-event precision / recall (VV): shows whether failures are over-detection (low P) or misses (low R).", "",
              "| Event | A P | A R | Cdelta_event P | Cdelta_event R | Cpct_event P | Cpct_event R |", "|---|---|---|---|---|---|---|"]
    for ev, ids in evs.items():
        a, d, p = (metr(res[m][ids].sum(0)) for m in ("A_VV", "Cdelta_event_VV", "Cpct_event_VV"))
        lines.append(f"| {ev} | {a['P']:.3f} | {a['R']:.3f} | {d['P']:.3f} | {d['R']:.3f} | {p['P']:.3f} | {p['R']:.3f} |")
    lines.append("")
    # thresholds
    lines += ["Thresholds in dB (VV): fixed A, event Otsu, calibrated (delta, pct, youden; event scale), oracle.", "",
              "| Event | A | Otsu(event) | Cdelta | Cpct | Cyouden | Oracle |", "|---|---|---|---|---|---|---|"]
    for ev, ids in evs.items():
        g = lambda k: detail[(ev, "VV", k)]
        jd = np.median(g("j_delta_event")); jp = np.median(g("j_pct_event")); jy = np.median(g("j_youden_event"))
        lines.append(f"| {ev} | {edge(g('A_j')):.1f} | {edge(g('otsu_ev_j')):.1f} | {edge(jd):.1f} | {edge(jp):.1f} | {edge(jy):.1f} | {edge(g('oracle_j')):.1f} |")
    lines.append("")
    # fallback frequency
    lines += ["Calibration fallback frequency (share of chips, VV): own = enough samples at that scale; event = chip fell back to event; fixed = fell back to A.", "",
              "| Method | own | event | fixed |", "|---|---|---|---|"]
    for m in flags:
        if m.endswith("_VV"):
            f = flags[m]
            lines.append(f"| {m} | {(f == 0).mean():.2f} | {(f == 1).mean():.2f} | {(f == 2).mean():.2f} |")
    lines.append("")
    lines += ["Per event, JRC-water samples (VV event-scale fallback to fixed A?):", "",
              "| Event | JRC water px | JRC land px | event calibration used? | JRC water inside hand-label water |", "|---|---|---|---|---|"]
    for ev, ids in evs.items():
        nj = sum(chips[i]["n_jrc_w"] for i in ids)
        nl = sum(chips[i]["n_jrc_l"] for i in ids)
        used = "yes" if (nj >= MIN_EVENT_WATER and nl >= MIN_LAND) else "NO (fixed A)"
        inl = sum(chips[i]["jrc_in_label"] * chips[i]["n_jrc_w"] for i in ids) / max(nj, 1)
        lines.append(f"| {ev} | {nj} | {nl} | {used} | {inl:.2f} |")
    lines.append("")
    out.extend(lines)
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["tune", "test"], required=True)
    ap.add_argument("--frozen", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "sen1floods11_frozen_params.json"))
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    man = json.load(open(DS + "/splits_manifest.json"))
    out = []
    if a.stage == "tune":
        names = man["tune"]["sen1floods11_train"] + man["tune"]["sen1floods11_valid"]
        chips = []
        for k, nm in enumerate(names):
            chips.append(load_summary(nm))
            if k % 50 == 0:
                print("  read", k, "/", len(names), flush=True)
        events = sorted({c["event"] for c in chips})
        res, flags, detail, frozen = run_tune(chips, events)
        frozen["events"] = events
        os.makedirs(os.path.dirname(os.path.abspath(a.frozen)), exist_ok=True)
        json.dump(frozen, open(a.frozen, "w"), indent=1)
        report("TUNING events, leave-one-event-out (each event scored with parameters chosen on the other 9)",
               chips, res, flags, detail, out)
        out += ["Frozen parameters (chosen on all 10 tuning events):", "", "```", json.dumps({k: v for k, v in frozen.items() if k != "LR"}, indent=1), "```", ""]
    else:
        frozen = json.load(open(a.frozen))
        sealed = man["sealed_test"]
        for key, title in (("sen1floods11_bolivia_heldout_event", "SEALED TEST: Bolivia (unseen event, 15 chips)"),
                           ("sen1floods11_official_test_seen_events", "SEALED TEST: official test chips (seen events, unseen chips)")):
            chips = [load_summary(nm) for nm in sealed[key]]
            res, flags, detail = run_test(chips, frozen)
            report(title, chips, res, flags, detail, out)
    txt = "\n".join(out)
    if a.out == "-":
        print(txt)
    else:
        open(a.out, "w").write(txt)


if __name__ == "__main__":
    main()
