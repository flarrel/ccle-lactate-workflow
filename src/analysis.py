"""Evaluate expression-based lactate prediction on held-out cancer lineages."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ALPHAS = [0.01, 0.1, 1, 10, 100, 1000]


def evaluate(cohort, features):
    groups = cohort["lineage"]
    if groups.nunique() < 5:
        raise ValueError("At least five lineages are required for grouped evaluation")
    x = cohort[features]
    y = cohort["lactate"]
    results = []
    folds = []
    for fold, (training, test) in enumerate(GroupKFold(n_splits=5).split(x, y, groups), 1):
        group_train, group_test = groups.iloc[training], groups.iloc[test]
        if set(group_train).intersection(group_test):
            raise RuntimeError("A held-out lineage appears in the training fold")
        estimator = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge())
        search = GridSearchCV(
            estimator,
            {"ridge__alpha": ALPHAS},
            scoring="neg_mean_absolute_error",
            cv=GroupKFold(n_splits=4),
        )
        search.fit(x.iloc[training], y.iloc[training], groups=group_train)

        training_median = y.iloc[training].median()
        lineage_medians = y.iloc[training].groupby(group_train).median()
        output = cohort.iloc[test][["model_id", "lineage", "lactate"]].copy()
        output["fold"] = fold
        output["ridge"] = search.predict(x.iloc[test])
        output["training_median"] = training_median
        output["lineage_median"] = group_test.map(lineage_medians).fillna(training_median)
        results.append(output)
        folds.append(
            {
                "fold": fold,
                "training_rows": len(training),
                "test_rows": len(test),
                "held_out_lineages": sorted(group_test.unique()),
                "alpha": search.best_params_["ridge__alpha"],
            }
        )
    predictions = pd.concat(results).sort_values("model_id").reset_index(drop=True)
    if len(predictions) != len(cohort) or not predictions["model_id"].is_unique:
        raise RuntimeError("Expected exactly one out-of-fold prediction per cell line")
    return predictions, folds


def summarize(predictions, folds):
    columns = ["ridge", "training_median", "lineage_median"]
    actual = predictions["lactate"]
    measures = {c: float(mean_absolute_error(actual, predictions[c])) for c in columns}
    error = abs(predictions["ridge"] - actual) - abs(predictions["training_median"] - actual)
    by_lineage = pd.DataFrame({"difference": error, "lineage": predictions["lineage"]})
    aggregates = by_lineage.groupby("lineage")["difference"].agg(["sum", "count"])
    rng = np.random.default_rng(972)
    draws = rng.integers(len(aggregates), size=(2000, len(aggregates)))
    differences = aggregates["sum"].to_numpy()[draws].sum(axis=1)
    counts = aggregates["count"].to_numpy()[draws].sum(axis=1)
    interval = np.quantile(differences / counts, [0.025, 0.975])
    return {
        "evaluation_rows": len(predictions),
        "lineages": len(aggregates),
        "mae": measures,
        "ridge_minus_training_median_mae": measures["ridge"] - measures["training_median"],
        "lineage_bootstrap_interval": interval.tolist(),
        "baseline_note": "The lineage model falls back to the training median for unseen lineages.",
        "folds": folds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", type=Path)
    parser.add_argument("qc", type=Path)
    args = parser.parse_args()
    cohort = pd.read_csv(args.cohort)
    qc = json.loads(args.qc.read_text())
    predictions, folds = evaluate(cohort, qc["features"])
    predictions.to_csv("predictions.csv", index=False, float_format="%.12g")
    Path("model.json").write_text(json.dumps(summarize(predictions, folds), indent=2) + "\n")


if __name__ == "__main__":
    main()
