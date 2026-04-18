#!/usr/bin/env python3
"""infercnvpy CNV inference using designated reference cell groups."""
import argparse
import infercnvpy as cnv
import scanpy as sc

parser = argparse.ArgumentParser()
parser.add_argument("in_h5ad")
parser.add_argument("out_h5ad")
parser.add_argument("--reference-key", required=True,
                    help="obs column identifying cell-type / cluster labels")
parser.add_argument("--reference-cat", required=True,
                    help="comma-separated list of values in reference-key to use as CNV-neutral reference")
parser.add_argument("--gtf", required=True, help="GTF file for gene coordinates")
args = parser.parse_args()

adata = sc.read_h5ad(args.in_h5ad)
cnv.io.genomic_position_from_gtf(args.gtf, adata=adata)
cnv.tl.infercnv(
    adata,
    reference_key=args.reference_key,
    reference_cat=[c.strip() for c in args.reference_cat.split(",")],
    window_size=250,
)
cnv.tl.pca(adata)
cnv.pp.neighbors(adata)
cnv.tl.leiden(adata)
cnv.tl.cnv_score(adata)
adata.write_h5ad(args.out_h5ad, compression="gzip")
print(f"wrote {adata.shape[0]} cells with cnv_score median "
      f"{float(adata.obs['cnv_score'].median()):.3f}")
