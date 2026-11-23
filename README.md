# CCLE lactate workflow

This local research workflow tests whether a small gene-expression panel predicts relative
lactate abundance in human cancer cell lines from unseen tissue lineages. It also checks
whether a local language model can answer questions about the analysis and its source literature
with verifiable citations.

## Run locally

The bundled runtime manifest targets Apple Silicon macOS. Install Python 3.12, Java 17, and Git.
Allow about 1.3 GB of downloads. The data, weights, environments, and generated files live in
the sibling runtime directory.

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
   Automated citation and number checks are followed by manual assessment of claim support.

## Outputs

The workflow publishes its results to `../runtime/results/`.

- `qc.json` records source provenance, joins, attrition, missingness, lineage counts, and variant QC.
- `predictions.csv` and `model.json` contain out-of-fold predictions, scores, and fold membership.
- `pathway.csv` and `pathway.json` show simulated trajectories, assumptions, and steady states.
- `evidence.json`, `answers.jsonl`, and `retained_sources.json` contain benchmark counts, generated
  answers and citations, and the source records used to check them.

## Data and interpretation

The inputs come from [DepMap Public 20Q2 version 4](https://doi.org/10.6084/m9.figshare.12280541.v4)
and [Li et al., Supplementary Table 1](https://doi.org/10.1038/s41591-019-0404-8), mirrored by
[EMBL-EBI BioStudies](https://www.ebi.ac.uk/biostudies/studies/S-EPMC6629041).
The model target is relative LC-MS signal for the same metabolite across cell lines. The
evaluation is internal to CCLE. The pathway parameters are illustrative and would need
longitudinal measurements for cell-line calibration. The evidence benchmark measures behavior
on these sources and questions only.
