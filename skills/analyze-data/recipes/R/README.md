# R recipes for `analyze-data`

Invoked non-interactively by the skill (and by `analysis-worker` when the backend for a question is `Rscript`). Each recipe reads its arguments from `commandArgs(trailingOnly=TRUE)` and writes its result to a file path passed in.

## Setup

See `docs/R_INSTALL.md` at the repo root. First-run bootstrap:

```bash
Rscript -e 'install.packages("renv", repos="https://cloud.r-project.org")'
Rscript -e 'renv::restore(project="skills/analyze-data/recipes/R", prompt=FALSE)'
```

## renv.lock maintenance

`renv.lock` in this directory is a **scaffold** listing the direct dependencies and their target Bioconductor 3.18 versions. Full transitive closure is materialized when a developer runs `renv::snapshot()` after a successful `renv::restore()`. When Bioconductor releases a new version (e.g., 3.19), update the `Bioconductor.Version` and the individual `Packages[*].Version` fields, then re-snapshot.

## Recipe inventory

| Recipe | Purpose | Example call |
|---|---|---|
| `idat_to_beta.R` | MethylationEPIC IDATs → beta matrix (noob) | `Rscript idat_to_beta.R <idat_dir> <sample_sheet.csv> <out_beta.tsv>` |
| `conumee_cnv.R` | minfi RGset → conumee arm-level CNV | `Rscript conumee_cnv.R <idat_dir> <sample_sheet.csv> <out_cnv_arms.tsv>` |
| `limma_voom_de.R` | edgeR+voom+limma moderated DE | `Rscript limma_voom_de.R <counts.tsv> <design.tsv> <contrast> <out_toptable.tsv>` |
| `fgsea_c6.R` | Ranked gene list → fgsea vs MSigDB C6 | `Rscript fgsea_c6.R <ranked_stats.tsv> <out_fgsea.tsv>` |
| `consensus_cluster.R` | Beta matrix → top-N MAD → ConsensusClusterPlus | `Rscript consensus_cluster.R <beta.tsv> <k_max> <out_assignments.tsv>` |
