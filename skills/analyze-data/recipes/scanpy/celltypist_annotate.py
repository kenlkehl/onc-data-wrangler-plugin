#!/usr/bin/env python3
"""CellTypist cell-type annotation against a named reference model."""
import argparse
import celltypist
import scanpy as sc

parser = argparse.ArgumentParser()
parser.add_argument("in_h5ad")
parser.add_argument("model_name", help="e.g. Immune_All_Low.pkl, Developing_Human_Brain.pkl")
parser.add_argument("out_h5ad")
parser.add_argument("--majority-voting", action="store_true", default=True)
args = parser.parse_args()

adata = sc.read_h5ad(args.in_h5ad)
celltypist.models.download_models(force_update=False, model=[args.model_name])
pred = celltypist.annotate(adata, model=args.model_name, majority_voting=args.majority_voting)
annotated = pred.to_adata()
annotated.write_h5ad(args.out_h5ad, compression="gzip")
print(f"wrote {annotated.shape[0]} cells; top labels: "
      f"{annotated.obs['majority_voting'].value_counts().head(5).to_dict()}")
