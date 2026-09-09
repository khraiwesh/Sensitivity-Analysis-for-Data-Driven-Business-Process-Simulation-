"""
Collect sensitivity results from the run folders in this directory into a CSV.

Mirrors the extract.py scripts in the student's Final archive, adapted to the
BPIC 2013 folder names and to the sa_<kpi> output layout this pipeline writes
(his runs used bare "cycle" / "waiting" / "processing" folder names).

Run it from inside any of the leaf folders, e.g.

    cd "Step 3/2013_morris" && python ../../extract.py --kpi cycle_time

Output goes to <method>_final_summary_<kpi>.csv next to the run folders, with
the same columns the archive uses:

    Morris:  dataset,seed,n_samples,name,mu_star,mu_star_conf
    Sobol:   dataset,seed,n_samples,group,S1,S1_conf,ST,ST_conf
"""

import argparse
import csv
import json
import re
from pathlib import Path

FOLDER = re.compile(r"^bpic2013_(sobol|morris)_(gw|nogw)_[nt](\d+)_seed(\d+)$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kpi", default="cycle_time",
                    help="cycle_time | waiting_time | processing_time")
    ap.add_argument("--dir", default=".", help="directory holding the run folders")
    args = ap.parse_args()

    base = Path(args.dir)
    rows, method = [], None

    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        m = FOLDER.match(folder.name)
        if not m:
            continue
        method, _gw, size, seed = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))

        sa_dir = folder / "sensitivity_analysis_outputs" / f"sa_{args.kpi}"
        if not sa_dir.exists():
            print(f"no sa_{args.kpi} in {folder.name}")
            continue

        name = ("morris_first_order.json" if method == "morris"
                else "sobol_first_and_total_order.json")
        path = sa_dir / name
        if not path.exists():
            print(f"missing {name} in {sa_dir}")
            continue

        data = json.load(open(path, encoding="utf-8"))
        if not data:
            print(f"EMPTY result in {folder.name} -- run needs repeating")
            continue

        key = "name" if method == "morris" else "group"
        for e in sorted(data, key=lambda x: x.get(key, "")):
            if method == "morris":
                rows.append([2013, seed, size, e["name"], e["mu_star"], e["mu_star_conf"]])
            else:
                rows.append([2013, seed, size, e["group"],
                             e["S1"], e["S1_conf"], e["ST"], e["ST_conf"]])

    if not rows:
        print("nothing collected")
        return

    header = (["dataset", "seed", "n_samples", "name", "mu_star", "mu_star_conf"]
              if method == "morris" else
              ["dataset", "seed", "n_samples", "group", "S1", "S1_conf", "ST", "ST_conf"])

    kpi_short = args.kpi.replace("_time", "")
    out = base / f"{method}_final_summary_{kpi_short}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
