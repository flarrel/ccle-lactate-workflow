"""Join CCLE modalities and record sample attrition and assay provenance."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from openpyxl import load_workbook
import pandas as pd


FEATURES = {
    "ENO1": 2023,
    "GAPDH": 2597,
    "LDHA": 3939,
    "LDHB": 3945,
    "PDHA1": 5160,
    "PDK1": 5163,
    "PKM": 5315,
    "SLC16A1": 6566,
    "SLC16A3": 9123,
}
ACH_ID = re.compile(r"ACH-\d{6}")


def require_unique_ids(frame, label):
    ids = frame["model_id"]
    if not ids.str.fullmatch(ACH_ID, na=False).all():
        raise ValueError(f"{label}: missing or malformed DepMap model identifiers")
    duplicates = ids[ids.duplicated(keep=False)].unique()
    if len(duplicates):
        raise ValueError(f"{label}: duplicate DepMap model identifiers: {', '.join(duplicates[:5])}")


def expression(path):
    labels = {f"{gene} ({entrez})": gene for gene, entrez in FEATURES.items()}
    with path.open(newline="") as stream:
        header = next(csv.reader(stream), [])
    if not header or header[0] not in {"", "DepMap_ID"}:
        raise ValueError("Expression: expected a DepMap model identifier in the first column")
    if any(header.count(column) != 1 for column in labels):
        raise ValueError("Expression: expected exactly one column for each declared gene and Entrez ID")
    first = "Unnamed: 0" if header[0] == "" else header[0]
    table = pd.read_csv(path, usecols=[first, *labels], dtype={first: "string"})
    table = table.rename(columns={first: "model_id", **labels})
    require_unique_ids(table, "Expression")
    values = table[list(FEATURES)].to_numpy(dtype=float)
    if np.isinf(values).any() or (values[np.isfinite(values)] < 0).any():
        raise ValueError("Expression: expected nonnegative finite log2(TPM+1) values or missing values")
    return table


def sample_metadata(path):
    fields = ["DepMap_ID", "CCLE_Name", "stripped_cell_line_name", "lineage"]
    table = pd.read_csv(path, usecols=fields, dtype="string").rename(columns={"DepMap_ID": "model_id"})
    require_unique_ids(table, "Sample metadata")
    return table



def read_lactate(path, metadata):
    sheet_name = "1-raw data"
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Metabolomics: missing required worksheet {sheet_name!r}")
        rows = workbook[sheet_name].iter_rows(values_only=True)
        header = next(rows, ())
        columns = [i for i, value in enumerate(header) if str(value).strip().casefold() == "lactate"]
        if len(columns) != 1 or columns[0] == 0:
            raise ValueError("Metabolomics: expected exactly one lactate column after the cell-line name")
        target = columns[0]
        readings = []
        for row in rows:
            name, reading = row[0], row[target]
            if name is None and reading is None:
                continue
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Metabolomics: expected a CCLE cell-line name in the first column")
            if reading in (None, "", "NA", "N/A"):
                reading = np.nan
            elif isinstance(reading, (int, float)) and not isinstance(reading, bool) and math.isfinite(reading) and reading > 0:
                reading = math.log10(reading)
            else:
                raise ValueError(f"Metabolomics: invalid standardized lactate peak area for {name}")
            readings.append((name.strip(), reading))
    finally:
        workbook.close()

    raw = pd.DataFrame(readings, columns=["CCLE_Name", "lactate"])
    if raw.empty or raw["CCLE_Name"].duplicated().any():
        raise ValueError("Metabolomics: expected nonempty data with unique CCLE cell-line names")
    exact_names = metadata.dropna(subset=["CCLE_Name"])
    exact_names = exact_names.loc[~exact_names["CCLE_Name"].duplicated(keep=False)]
    mapped = raw.merge(exact_names[["CCLE_Name", "model_id"]], on="CCLE_Name", validate="one_to_one")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return mapped[["model_id", "lactate"]], {
        "source": "Li et al. 2019 Supplementary Table 1",
        "source_sha256": digest,
        "worksheet": sheet_name,
        "units": "log10 of batch-standardized LC-MS lactate peak area",
        "source_rows": len(raw),
        "source_rows_missing_lactate": int(raw["lactate"].isna().sum()),
        "rows_without_unique_exact_ccle_name_match": len(raw) - len(mapped),
        "join": "Exact unique CCLE_Name to DepMap 20Q2 model ID",
        "missing_lactate_policy": "Excluded; no lactate value imputed",
    }


def variant_qc(path, cohort_ids):
    fields = ["DepMap_ID", "Hugo_Symbol", "Entrez_Gene_Id", "Variant_Classification", "NCBI_Build"]
    overall = Counter()
    panel = Counter()
    builds = Counter()
    matched = set()
    rows = 0
    with path.open(newline="") as stream:
        header = stream.readline()
    delimiter = "\t" if "\t" in header else ","
    for chunk in pd.read_csv(path, sep=delimiter, usecols=fields, dtype="string", chunksize=100_000):
        rows += len(chunk)
        rows_in_cohort = chunk.loc[chunk["DepMap_ID"].isin(cohort_ids)]
        matched.update(rows_in_cohort["DepMap_ID"])
        overall.update(rows_in_cohort["Variant_Classification"].fillna("missing"))
        builds.update(rows_in_cohort["NCBI_Build"].fillna("missing"))
        expected = rows_in_cohort["Hugo_Symbol"].map({gene: str(id_) for gene, id_ in FEATURES.items()})
        verified = expected.notna() & expected.eq(rows_in_cohort["Entrez_Gene_Id"]).fillna(False)
        panel.update(rows_in_cohort.loc[verified, "Hugo_Symbol"])
    return {
        "source_rows": rows,
        "cohort_lines_with_any_listed_variant": len(matched),
        "cohort_lines_without_listed_variant": len(cohort_ids - matched),
        "cohort_variant_rows_by_class": dict(sorted(overall.items())),
        "cohort_variant_rows_by_reference_build": dict(sorted(builds.items())),
        "panel_variant_rows_by_gene_with_matching_entrez_id": dict(sorted(panel.items())),
        "interpretation": "A line without a listed variant is not inferred to have tested wild type.",
    }


def prepare(expression_path, mutations_path, metadata_path, metabolomics_path):
    expr = expression(expression_path)
    metadata = sample_metadata(metadata_path)
    metabolites, assay = read_lactate(metabolomics_path, metadata)
    require_unique_ids(metabolites, "Metabolomics")
    paired = expr.merge(metabolites, on="model_id", validate="one_to_one")
    with_metadata = paired.merge(metadata[["model_id", "lineage"]], on="model_id", validate="one_to_one")
    cohort = with_metadata.dropna(subset=["lactate", "lineage"]).sort_values("model_id")
    if cohort.empty:
        raise ValueError("No cell lines have expression, a finite lactate label, and lineage metadata")
    ids = set(cohort["model_id"])
    qc = {
        "expression_rows": len(expr),
        "metadata_rows": len(metadata),
        "mapped_metabolomics_rows": len(metabolites),
        "expression_without_metabolomics_rows": len(set(expr["model_id"]) - set(metabolites["model_id"])),
        "metabolomics_without_expression_rows": len(set(metabolites["model_id"]) - set(expr["model_id"])),
        "matched_expression_metabolomics_rows": len(paired),
        "matched_metadata_rows": len(with_metadata),
        "excluded_missing_lactate_or_lineage_rows": len(with_metadata) - len(cohort),
        "modeling_rows": len(cohort),
        "lineage_counts": cohort["lineage"].value_counts().sort_index().to_dict(),
        "features": list(FEATURES),
        "feature_annotation_entrez": FEATURES,
        "missing_feature_counts": cohort[list(FEATURES)].isna().sum().to_dict(),
        "expression_units": "log2(TPM+1)",
        "metabolomics_assay": assay,
        "variant_qc": variant_qc(mutations_path, ids),
    }
    return cohort, qc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("expression", "mutations", "metadata", "metabolomics"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    cohort, qc = prepare(args.expression, args.mutations, args.metadata, args.metabolomics)
    cohort.to_csv("cohort.csv", index=False, float_format="%.12g")
    Path("qc.json").write_text(json.dumps(qc, indent=2) + "\n")


if __name__ == "__main__":
    main()
