#!/usr/bin/env python3
"""Normalize → HVG → PCA → neighbors → Leiden → UMAP."""
import argparse
import scanpy as sc

parser = argparse.ArgumentParser()
parser.add_argument("in_h5ad")
parser.add_argument("out_h5ad")
parser.add_argument("--n-hvg", type=int, default=3000)
parser.add_argument("--n-pcs", type=int, default=50)
parser.add_argument("--resolution", type=float, default=0.8)
args = parser.parse_args()

adata = sc.read_h5ad(args.in_h5ad)
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, n_top_genes=args.n_hvg, flavor="seurat_v3", subset=False)
adata.raw = adata
adata = adata[:, adata.var["highly_variable"]].copy()
sc.pp.scale(adata, max_value=10)
sc.tl.pca(adata, n_comps=args.n_pcs, random_state=42)
sc.pp.neighbors(adata, n_pcs=args.n_pcs, random_state=42)
sc.tl.leiden(adata, resolution=args.resolution, random_state=42)
sc.tl.umap(adata, random_state=42)
adata.write_h5ad(args.out_h5ad, compression="gzip")
print(f"wrote {adata.shape[0]} cells with {adata.obs['leiden'].nunique()} leiden clusters")
