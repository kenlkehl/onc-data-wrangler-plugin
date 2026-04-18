# scanpy recipes for `analyze-data`

Python snRNA-seq / scRNA-seq recipes invoked non-interactively. Each script reads its arguments via `argparse`, works on AnnData on disk (`.h5ad`) where possible, and is memory-bounded via anndata-backed mode for large matrices (tested up to ~43k nuclei × 15k genes).

## Setup

From the plugin repo root:

```bash
pip install -r skills/analyze-data/recipes/scanpy/requirements.txt
```

## Recipe inventory

| Recipe | Purpose | Example call |
|---|---|---|
| `load_10x.py` | 10X Genomics mtx/h5 → `.h5ad` with cell/gene metadata | `python load_10x.py <mtx_dir_or_h5> <out.h5ad>` |
| `qc.py` | Per-cell QC metrics + filter (mito %, gene count, doublets) | `python qc.py <in.h5ad> <out.h5ad>` |
| `hvg_leiden.py` | Normalize → HVG → PCA → neighbors → Leiden → UMAP | `python hvg_leiden.py <in.h5ad> <out.h5ad>` |
| `celltypist_annotate.py` | CellTypist per-cell annotation against a named model | `python celltypist_annotate.py <in.h5ad> <model_name> <out.h5ad>` |
| `infercnv.py` | infercnvpy CNV inference from reference groups | `python infercnv.py <in.h5ad> <reference_groups_csv> <out.h5ad>` |
