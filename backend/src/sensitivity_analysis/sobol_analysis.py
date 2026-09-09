from SALib.analyze import sobol as sobol_analyze
import numpy as np
import pandas as pd


def sobol_analysis(
    stat_type: str,
    df_output_metric: pd.DataFrame,
    problem: dict,
    calc_second_order: bool,
    seed: int,
    cases_list: list[int],
    expected_total_samples: int,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """
    Run (grouped) Sobol sensitivity analysis for a given KPI statistic
    across multiple case sizes.

    Parameters
    ----------
    stat_type : str
        Name of the statistic column in `df_output_metric`,
        e.g. "avg", "min", "max", or "total".
    df_output_metric : pd.DataFrame
        DataFrame containing the KPI values per sample and case size.
        Must include at least:
            ["num_cases", "sample_id", stat_type].
    problem : dict
        SALib Sobol problem definition. Must define either:
            - "num_vars" (int), or
            - "names" (list of parameter names),
        and may optionally include "groups" for grouped Sobol analysis.
    calc_second_order : bool
        If True, compute second-order indices S2 and S2_conf in addition
        to first-order (S1) and total-order (ST) indices.
    seed : int
        Random seed for the Sobol analysis (used internally by SALib).
    cases_list : list[int]
        List of num_cases values (e.g. [50, 100, 200]) for which the
        analysis is repeated. For each value, Y is taken from the rows
        with that num_cases.
    expected_total_samples : int
        The total number of samples that were *intended* to be simulated
        (i.e. the size of the original Saltelli/Sobol design matrix,
        derived from the sample chunk files at simulation time). Every
        sample_id in range(expected_total_samples) MUST be present in
        `df_output_metric` for a given `num_cases`, otherwise the analysis
        is aborted with an explicit error (missing samples are never
        imputed or silently skipped).

    Returns
    -------
    sobol_results_first_and_total_order : pd.DataFrame
        First- and total-order Sobol indices aggregated for all cases.
        Columns:
            ["group", "cases", "S1", "S1_conf", "ST", "ST_conf"],
        sorted by ["cases", "ST"] (descending ST within each cases).
    sobol_results_second_order : pd.DataFrame or None
        If `calc_second_order` is True and the analysis succeeds:
            Columns:
                ["group_i", "group_j", "S2", "S2_conf", "cases"],
            with upper-triangular S2 pairs for each cases value.
        If `calc_second_order` is False, returns None.

    Raises
    ------
    RuntimeError
        If, for any `num_cases` value, one or more sample_ids in
        `range(expected_total_samples)` are missing from
        `df_output_metric` (e.g. because the underlying simulation
        failed/errored for those samples). This is a hard failure:
        missing samples are never imputed, and no partial/null results
        are written.
    """

    if stat_type not in df_output_metric.columns:
        raise ValueError(
            f"stat_type='{stat_type}' is not a column in df_output_metric "
            f"(available: {list(df_output_metric.columns)})"
        )

    if "num_cases" not in df_output_metric.columns or "sample_id" not in df_output_metric.columns:
        raise ValueError("df_output_metric must contain 'num_cases' and 'sample_id' columns")

    if not isinstance(expected_total_samples, (int, np.integer)) or expected_total_samples <= 0:
        raise ValueError(
            f"expected_total_samples must be a positive integer, got: {expected_total_samples!r}"
        )

    # Determine dimensionality & group names from problem
    if not isinstance(problem, dict):
        raise TypeError("problem must be a dict compatible with SALib's Sobol problem definition")

    # num_vars: number of variables
    if "num_vars" in problem:
        num_vars = int(problem["num_vars"])
    elif "names" in problem:
        num_vars = len(problem["names"])
    else:
        raise ValueError("problem must contain 'num_vars' or 'names' to determine dimensionality")

    # Group handling
    if "groups" in problem and problem["groups"] is not None:
        groups = list(problem["groups"])
        # preserve first-appearance order for group names
        seen = {}
        group_names = [seen.setdefault(g, g) for g in groups if g not in seen]
        group_names_len = len(group_names)
    else:
        group_names = [f"x{i}" for i in range(num_vars)]
        group_names_len = num_vars

    group_rows: list[dict] = []
    group_rows_second_order: list[dict] = []

    # Loop over each num_cases
    for cases in cases_list:
        # Filter df_output_metric by num_cases
        df_cases = df_output_metric[df_output_metric["num_cases"] == cases].copy()

        if df_cases.empty:
            # Nothing for this case value → skip
            continue

        # --- Explicit completeness check (fail fast, never impute) ---
        # Every sample_id in [0, expected_total_samples) must be present exactly
        # once. Any gap means one or more simulations failed/errored for this
        # num_cases, which would silently misalign Y with the Sobol design
        # matrix if left unchecked (SALib requires Y in exact generation order
        # with length == expected_total_samples).
        present_ids = set(df_cases["sample_id"].astype(int).tolist())
        expected_ids = set(range(expected_total_samples))
        missing_ids = sorted(expected_ids - present_ids)
        unexpected_ids = sorted(present_ids - expected_ids)
        duplicate_ids = sorted(
            df_cases["sample_id"].astype(int).value_counts().loc[lambda s: s > 1].index.tolist()
        )

        if missing_ids or unexpected_ids or duplicate_ids:
            raise RuntimeError(
                f"Sobol analysis aborted for num_cases={cases}: incomplete/invalid sample "
                f"coverage. Expected {expected_total_samples} samples (sample_id 0.."
                f"{expected_total_samples - 1}), found {len(present_ids)} unique sample_id(s). "
                f"Missing: {len(missing_ids)} (e.g. {missing_ids[:10]}). "
                f"Unexpected (out of range): {len(unexpected_ids)} (e.g. {unexpected_ids[:10]}). "
                f"Duplicated: {len(duplicate_ids)} (e.g. {duplicate_ids[:10]}). "
                f"Missing samples are never imputed - fix the underlying simulation failures "
                f"and re-run before performing Sobol analysis."
            )

        # Build Y using the chosen stat_type, sorted by sample_id
        Y = (
            df_cases.sort_values("sample_id")[stat_type]
            .astype(float)
            .to_numpy()
        )

        # Run Sobol analysis. Any failure here (e.g. degenerate/constant data)
        # is allowed to propagate - results are never silently replaced with
        # null placeholders.
        sobol_analysis_result = sobol_analyze.analyze(
            problem=problem,
            Y=Y,
            calc_second_order=calc_second_order,
            print_to_console=False,
            seed=seed,
        )

        # ---- First & total order ----
        S1 = np.asarray(sobol_analysis_result.get("S1", np.full(group_names_len, np.nan)))
        S1_conf = np.asarray(sobol_analysis_result.get("S1_conf", np.full(group_names_len, np.nan)))
        ST = np.asarray(sobol_analysis_result.get("ST", np.full(group_names_len, np.nan)))
        ST_conf = np.asarray(sobol_analysis_result.get("ST_conf", np.full(group_names_len, np.nan)))

        for g_name, s1, s1c, st, stc in zip(group_names, S1, S1_conf, ST, ST_conf):
            group_rows.append(
                {
                    "cases": cases,
                    "group": g_name,
                    "S1": float(s1),
                    "S1_conf": float(s1c),
                    "ST": float(st),
                    "ST_conf": float(stc),
                }
            )

        # ---- Second order (S2) ----
        if calc_second_order:
            S2 = np.asarray(sobol_analysis_result.get("S2", np.full((group_names_len, group_names_len), np.nan)), dtype=float)
            S2_conf = np.asarray(sobol_analysis_result.get("S2_conf", np.full((group_names_len, group_names_len), np.nan)), dtype=float)

            if S2.ndim != 2 or S2.shape[0] != S2.shape[1] or S2.shape[0] != len(group_names):
                raise ValueError(
                    f"S2 must be a square matrix with size == len(group_names); "
                    f"got S2.shape={S2.shape}, len(group_names)={len(group_names)}"
                )

            iu = np.triu_indices_from(S2, k=1)

            for i, j in zip(*iu):
                group_rows_second_order.append(
                    {
                        "cases": cases,
                        "group_i": group_names[i],
                        "group_j": group_names[j],
                        "S2": float(S2[i, j]),
                        "S2_conf": float(S2_conf[i, j]),
                    }
                )

    # Build DataFrames from collected rows
    sobol_results_first_and_total_order = (
        pd.DataFrame(group_rows)
        .sort_values(["cases", "ST"], ascending=[True, False])
        .reset_index(drop=True)
    )

    if calc_second_order:
        sobol_results_second_order = (
            pd.DataFrame(group_rows_second_order)
            .sort_values(["cases", "S2"], ascending=[True, False])
            .reset_index(drop=True)
        )
    else:
        sobol_results_second_order = None

    return sobol_results_first_and_total_order, sobol_results_second_order
