from SALib.analyze import morris as morris_analyze
import numpy as np
import pandas as pd


def morris_analysis(
    stat_type: str,
    df_output_metric: pd.DataFrame,
    problem: dict,
    samples: np.ndarray,
    conf_level: float,
    num_levels: int,
    seed: int,
    cases_list: list[int],
    expected_total_samples: int,
) -> pd.DataFrame:
    """
    Run a Morris sensitivity analysis for a chosen KPI across multiple
    case sizes and collect the results in a single table.

    Behaviour
    ---------
    For each value in `cases_list`, the function:
      - filters `df_output_metric` to rows with that `num_cases`,
      - verifies every sample_id in range(expected_total_samples) is present
        exactly once (raises explicitly otherwise - missing samples are
        never imputed),
      - sorts by `sample_id` and extracts the column given by `stat_type`
        as the response vector `Y`,
      - calls `SALib.analyze.morris.analyze(...)` with the provided
        `problem`, `samples` and analysis options,
      - extracts Morris indices (mu, mu_star, mu_star_conf, sigma),
      - appends one row per parameter/group to the results list.

    Parameters
    ----------
    stat_type : str
        Name of the KPI/statistic column in `df_output_metric`
        (e.g. "avg", "min", "max", "total"). Must exist as a column.
    df_output_metric : pd.DataFrame
        Simulation output table with at least:
          - "num_cases" : int, scenario / case size identifier,
          - "sample_id" : int, index matching the design matrix rows,
          - `stat_type` : float, KPI value for each (num_cases, sample_id).
    problem : dict
        SALib Morris problem definition; must contain either
        "num_vars" or "names" to determine dimensionality.
    samples : np.ndarray
        Morris design matrix X (U_var), shape (n_rows, n_vars), used
        to generate the simulations that produced `df_output_metric`.
    conf_level : float
        Confidence level passed to `morris_analyze.analyze` for
        estimating `mu_star_conf` (e.g. 0.95).
    num_levels : int
        Number of levels in the Morris design (must match the design
        used to create `samples`).
    seed : int
        Random seed for the Morris analysis (used internally by SALib).
    cases_list : list[int]
        List of `num_cases` values for which the Morris analysis will
        be computed and reported.
    expected_total_samples : int
        The total number of samples that were *intended* to be simulated
        (i.e. the number of rows of the Morris design matrix at sampling
        time). Every sample_id in range(expected_total_samples) MUST be
        present in `df_output_metric` for a given `num_cases`, otherwise
        the analysis is aborted with an explicit error.

    Returns
    -------
    pd.DataFrame
        If at least one case is successfully analyzed, returns a DataFrame
        with columns:
          - "name"        : parameter or group name from the analysis,
          - "cases"       : num_cases value for this analysis run,
          - "mu"          : mean elementary effect (signed),
          - "mu_star"     : mean absolute elementary effect,
          - "mu_star_conf": confidence interval half-width for mu_star,
          - "sigma"       : standard deviation of elementary effects.
        Rows are sorted by ["cases", "mu_star"] (mu_star descending).

    Raises
    ------
    RuntimeError
        If, for any `num_cases` value, one or more sample_ids in
        range(expected_total_samples) are missing from `df_output_metric`
        (e.g. because the underlying simulation failed/errored for those
        samples). Missing samples are never imputed.
    """

    # Basic checks
    if stat_type not in df_output_metric.columns:
        raise ValueError(
            f"stat_type='{stat_type}' is not a column in df_output_metric "
            f"(available: {list(df_output_metric.columns)})"
        )

    if "num_cases" not in df_output_metric.columns or "sample_id" not in df_output_metric.columns:
        raise ValueError("df_output_metric must contain 'num_cases' and 'sample_id' columns")

    if not isinstance(problem, dict):
        raise TypeError("problem must be a dict compatible with SALib's Morris problem definition")

    if not isinstance(samples, np.ndarray):
        raise TypeError("samples must be a numpy.ndarray")

    if not isinstance(expected_total_samples, (int, np.integer)) or expected_total_samples <= 0:
        raise ValueError(
            f"expected_total_samples must be a positive integer, got: {expected_total_samples!r}"
        )

    # Determine dimensionality num_vars
    if "num_vars" in problem:
        num_vars = int(problem["num_vars"])
    elif "names" in problem:
        num_vars = len(problem["names"])
    else:
        raise ValueError("problem must contain 'num_vars' or 'names' to determine dimensionality")

    n_rows, n_cols = samples.shape
    if n_cols != num_vars:
        raise ValueError(
            f"Design matrix samples has {n_cols} columns but problem expects {num_vars} variables."
        )

    group_rows: list[dict] = []

    for cases in cases_list:
        # --- Filter df_output_metric for this num_cases ---
        df_cases = df_output_metric[df_output_metric["num_cases"] == cases].copy()

        if df_cases.empty:
            print(f"⚠️ No rows in df_output_metric for num_cases={cases}; skipping")
            continue

        # --- Explicit completeness check (fail fast, never impute) ---
        # Every sample_id in [0, expected_total_samples) must be present exactly
        # once. Any gap means one or more simulations failed/errored for this
        # num_cases, which would silently misalign Y with the Morris design
        # matrix `samples` if left unchecked.
        present_ids = set(df_cases["sample_id"].astype(int).tolist())
        expected_ids = set(range(expected_total_samples))
        missing_ids = sorted(expected_ids - present_ids)
        unexpected_ids = sorted(present_ids - expected_ids)
        duplicate_ids = sorted(
            df_cases["sample_id"].astype(int).value_counts().loc[lambda s: s > 1].index.tolist()
        )

        if missing_ids or unexpected_ids or duplicate_ids:
            raise RuntimeError(
                f"Morris analysis aborted for num_cases={cases}: incomplete/invalid sample "
                f"coverage. Expected {expected_total_samples} samples (sample_id 0.."
                f"{expected_total_samples - 1}), found {len(present_ids)} unique sample_id(s). "
                f"Missing: {len(missing_ids)} (e.g. {missing_ids[:10]}). "
                f"Unexpected (out of range): {len(unexpected_ids)} (e.g. {unexpected_ids[:10]}). "
                f"Duplicated: {len(duplicate_ids)} (e.g. {duplicate_ids[:10]}). "
                f"Missing samples are never imputed - fix the underlying simulation failures "
                f"and re-run before performing Morris analysis."
            )

        # Prepare Y aligned to the Morris design rows
        Y = (
            df_cases.sort_values("sample_id")[stat_type]
            .astype(float)
            .to_numpy()
        )

        if len(Y) != n_rows:
            raise RuntimeError(
                f"len(Y)={len(Y)} != rows in Morris design matrix ({n_rows}) for cases={cases}. "
                f"This indicates the stored design matrix does not match "
                f"expected_total_samples={expected_total_samples}; aborting rather than "
                f"silently skipping."
            )

        # Run Morris analysis. Any failure here is allowed to propagate - results
        # are never silently skipped/replaced with null placeholders.
        morris_analysis_result = morris_analyze.analyze(
            problem=problem,
            X=samples,
            Y=Y,
            conf_level=conf_level,
            num_levels=num_levels,
            print_to_console=False,
            seed=seed,
        )

        group_names = morris_analysis_result.get("names", None)

        if group_names is None:
            # Fallback: use generic names if missing
            group_names = [f"x{i}" for i in range(num_vars)]

        mu =          np.asarray(morris_analysis_result.get("mu",             np.full(num_vars, np.nan)))
        mu_star =     np.asarray(morris_analysis_result.get("mu_star",        np.full(num_vars, np.nan)))
        mu_star_conf = np.asarray(morris_analysis_result.get("mu_star_conf",  np.full(num_vars, np.nan)))
        sigma =       np.asarray(morris_analysis_result.get("sigma",          np.full(num_vars, np.nan)))

        for group_name, a, b, c, s in zip(group_names, mu, mu_star, mu_star_conf, sigma):
            group_rows.append(
                {
                    "name": group_name,
                    "cases": cases,
                    "mu": float(a),
                    "mu_star": float(b),
                    "mu_star_conf": float(c),
                    "sigma": float(s),
                }
            )

    if not group_rows:
        return pd.DataFrame(
            columns=["name", "cases", "mu", "mu_star", "mu_star_conf", "sigma"]
        )

    return (
        pd.DataFrame(group_rows)
        .sort_values(["cases", "mu_star"], ascending=[True, False])
        .reset_index(drop=True)
    )
