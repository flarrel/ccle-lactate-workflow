# Results

## Cohort and prediction

The original study's standardized peak-area sheet supplied 928 cell-line rows. Exact CCLE
names mapped 910 rows uniquely to the DepMap release. Of those, 899 had matching expression
and lineage metadata. One lacked a lactate reading and was excluded. The remaining 898 cell
lines represent 24 lineages, with all nine expression features present. Variant annotation
QC covered 865,967 listed rows for those cell lines. The prediction model uses expression
features only.

Across five lineage-held-out folds, ridge MAE was **0.2965** compared with **0.3110** for the
training median, in log10 standardized peak-area units. The unseen-lineage baseline also
returned 0.3110 because it falls back to that median. The paired lineage bootstrap interval
for ridge minus baseline MAE was **−0.0421 to 0.0123**, conditional on the fitted out-of-fold
predictions. It includes zero. Validation on an independent cohort would be needed to
establish transfer beyond CCLE.

The three illustrative scenarios had analytical steady states of 4, 6, and 8 relative
units for reference, higher supply, and slower clearance, respectively. The numerical
trajectories matched the analytical solution within the test tolerance. The steady states
are properties of the assumed model. CCLE abundance measurements do not identify the
production or clearance parameters.

## Literature evidence and model behavior

The benchmark used 12 answerable and 8 unanswerable questions. Retrieval alone found the
designated record in the top three for 11 of 12 answerable questions. It also returned
related records for all 8 unanswerable questions. Related records can lack evidence for
the specific claim.

Qwen returned valid JSON for all 20 questions. Five answerable responses used an exact
designated citation. Manual review found seven answers with correct content and three
that were both correct and used the exact supporting citation ID. The model abstained
on 4 of 8 unanswerable questions and on 2 of 12 answerable questions. Among 14 attempted
answers, 8 passed the automatic citation and number check, while 7 contained incorrect
or unsupported content on manual review.

- The model answered 225 when the source gave 148 as the number of metabolites whose variation
  exceeded the stated lineage threshold. Both numbers appeared in the same source, so the
  numeric check passed.
- The model answered TSV when the source described a change from TSV to CSV. The citation
  matched and the answer reversed the direction.
- The model gave ridge MAE as the answer to a question about prospective clinical sensitivity.
  The number appeared in the cited record, which supplied no clinical validation result.
- The model supplied the correct reference steady state with a bracketed citation ID. The
  parser requires an exact record ID, so it rejected the bracketed value.

The corpus contains eight curated source summaries and three generated run records. The
small benchmark measures this workflow configuration. A scientist should review generated
claims against the cited record before reuse.

## Workflow checks

The full workflow completed all four Nextflow stages. A fresh repository snapshot produced
byte-identical copies of all eight published outputs with the same pinned inputs. A resumed
run reused all four completed stages. A separate run with an invalid expression header
failed during preparation before creating model results.
