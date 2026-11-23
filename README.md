# CCLE lactate workflow

A local Nextflow pipeline for studying lactate in the Cancer Cell Line Encyclopedia (CCLE).
It joins RNA expression, lactate measurements, and cell-line metadata, then tests whether
expression predicts relative lactate abundance in tissue lineages held out from training.
It also audits variant annotations, simulates lactate supply and clearance, and evaluates
whether a local language model can cite evidence for answers about the data and results.

See the [results from the original run](RESULTS.md) for prediction errors, citation failures,
and reproducibility checks.

## Run locally

Use macOS on Apple Silicon with Python 3.12 and Java 17. Allow about 1.3 GB of downloads.
The workflow stores datasets, model weights, dependencies, and results in the sibling
`runtime/` directory.

```sh
./bootstrap
./run
./run -resume
../runtime/venv/bin/python -m unittest discover -s tests -v
```

`bootstrap` verifies release checksums before using data or executable assets. Nextflow runs
locally without containers. The language model runs in a local CPU process.

## Analysis

1. **Prepare.** Match the original CCLE lactate sheet against DepMap 20Q2 by unique exact cell-line
   name and join expression by DepMap model ID. Exclude missing lactate and transform observed
   standardized peak areas with log10. Audit selected gene symbols against their Entrez identifiers.
   Summarize listed somatic variants for the retained cohort separately from the prediction inputs.
2. **Regress.** Use five outer group folds by tissue lineage and four inner group folds for
   ridge regularization. Fit imputation and scaling inside training folds. Compare with the
   training median and the lineage baseline, which falls back to the training median for unseen
   lineages. Report MAE and a paired, lineage-resampled interval conditional on the fixed predictions.
3. **Simulate.** Simulate an illustrative single lactate pool with constant supply and first-order
   clearance. Compare the numerical solution against the analytical trajectory and report how
   the steady state changes under different assumed parameters.
4. **Check evidence.** Index source summaries and observed workflow facts in SQLite FTS5. Compare
   retrieval recall at three with the local model's citation behavior on a fixed, small benchmark.
   Check citation IDs and numbers automatically, then review whether the cited records
   support the answers.

## Outputs

The workflow publishes its results to `../runtime/results/`. When changing inputs, pass a fresh
`--outdir` to keep the new run’s artifacts together.

- `qc.json` records source provenance, joins, attrition, missingness, lineage counts, and variant QC.
- `predictions.csv` and `model.json` contain out-of-fold predictions, scores, and fold membership.
- `pathway.csv` and `pathway.json` show simulated trajectories, assumptions, and steady states.
- `evidence.json`, `answers.jsonl`, and `retained_sources.json` contain benchmark counts, generated
  answers and citations, and the source records used to check them.

## Data and interpretation

The inputs come from [DepMap Public 20Q2 version 4](https://doi.org/10.6084/m9.figshare.12280541.v4)
and [Li et al., Supplementary Table 1](https://doi.org/10.1038/s41591-019-0404-8), mirrored by
[EMBL-EBI BioStudies](https://www.ebi.ac.uk/biostudies/studies/S-EPMC6629041).
The prediction target is relative LC-MS lactate signal across CCLE cell lines. The pathway
model uses assumed parameters. Calibrating it for a cell line would require longitudinal
measurements. The language model results apply to the sources and questions in this run.
