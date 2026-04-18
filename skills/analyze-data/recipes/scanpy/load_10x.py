#!/usr/bin/env python3
"""Load 10X Genomics output into AnnData."""
import argparse
import os
import scanpy as sc

parser = argparse.ArgumentParser()
parser.add_argument("input_path", help="Either a 10X mtx directory (with matrix.mtx.gz, barcodes.tsv.gz, features.tsv.gz) or a filtered_feature_bc_matrix.h5")
parser.add_argument("out_h5ad")
args = parser.parse_args()

if os.path.isdir(args.input_path):
    adata = sc.read_10x_mtx(args.input_path, var_names="gene_symbols", cache=False)
else:
    adata = sc.read_10x_h5(args.input_path)
adata.var_names_make_unique()
adata.write_h5ad(args.out_h5ad, compression="gzip")
print(f"wrote {adata.shape[0]} cells × {adata.shape[1]} genes to {args.out_h5ad}")
