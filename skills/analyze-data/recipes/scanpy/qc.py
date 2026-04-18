#!/usr/bin/env python3
"""Per-cell QC: mito %, gene count, UMI count, doublet scoring, filter."""
import argparse
import scanpy as sc
import scrublet as scr

parser = argparse.ArgumentParser()
parser.add_argument("in_h5ad")
parser.add_argument("out_h5ad")
parser.add_argument("--min-genes", type=int, default=500)
parser.add_argument("--max-pct-mito", type=float, default=10.0)
parser.add_argument("--mito-prefix", default="MT-")
args = parser.parse_args()

adata = sc.read_h5ad(args.in_h5ad)
adata.var["mito"] = adata.var_names.str.startswith(args.mito_prefix)
sc.pp.calculate_qc_metrics(adata, qc_vars=["mito"], inplace=True, percent_top=None, log1p=False)

sc.pp.filter_cells(adata, min_genes=args.min_genes)
adata = adata[adata.obs["pct_counts_mito"] < args.max_pct_mito].copy()

scrub = scr.Scrublet(adata.X)
adata.obs["doublet_score"], adata.obs["predicted_doublet"] = scrub.scrub_doublets(verbose=False)
adata = adata[~adata.obs["predicted_doublet"]].copy()

adata.write_h5ad(args.out_h5ad, compression="gzip")
print(f"wrote {adata.shape[0]} cells × {adata.shape[1]} genes after QC")
