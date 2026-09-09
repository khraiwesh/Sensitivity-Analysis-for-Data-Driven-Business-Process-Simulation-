import sys
import pandas as pd

NAME_TO_CODE = {
    "Arrival Calendar": "AC",
    "Arrival Distribution": "AD",
    "Resource Calendars": "RC",
    "Resource Numbers": "RN",
    "Tasks and Resources Distributions": "TR",
    "Gateways": "GW",
}


def load_one(path, dataset_label, method, value_col):
    df = pd.read_csv(path)
    df = df.rename(columns={
        "n_samples": "sample_size",
        "group": "parameter",
        "name": "parameter",
        value_col: "value",
    })
    df["parameter"] = df["parameter"].map(NAME_TO_CODE)
    if df["parameter"].isna().any():
        bad = df[df["parameter"].isna()]
        raise ValueError(f"Unrecognised group name(s) in {path}:\n{bad}")
    df["method"] = method
    df["dataset"] = dataset_label
    return df[["dataset", "method", "seed", "sample_size", "parameter", "value"]]


def main():
    dataset_label, sobol_path, morris_path, output_csv = sys.argv[1:5]
    parts = []
    if sobol_path.lower() != "none":
        parts.append(load_one(sobol_path, dataset_label, "sobol", "ST"))
    if morris_path.lower() != "none":
        parts.append(load_one(morris_path, dataset_label, "morris", "mu_star"))
    out = pd.concat(parts, ignore_index=True)
    out.to_csv(output_csv, index=False)
    print(out.groupby(["dataset", "method"])["parameter"].apply(lambda s: sorted(s.unique())))
    print("\nTotal rows:", len(out))
    print(f"Saved to {output_csv}")


if __name__ == "__main__":
    main()
