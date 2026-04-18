#!/usr/bin/env Rscript
# Usage: Rscript limma_voom_de.R <counts.tsv> <design.tsv> <contrast> <out_toptable.tsv>
# counts.tsv: gene × sample integer counts, tab-delimited, gene IDs in first column.
# design.tsv: sample × factor columns (first column sample_id, must match counts columns).
# contrast : string passed to makeContrasts, e.g. "groupTumor - groupNormal".
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4)
suppressPackageStartupMessages({ library(edgeR); library(limma) })
counts <- as.matrix(read.table(args[1], sep = "\t", header = TRUE, row.names = 1, check.names = FALSE))
meta   <- read.table(args[2], sep = "\t", header = TRUE, row.names = 1, check.names = FALSE)
meta   <- meta[colnames(counts), , drop = FALSE]
design <- model.matrix(as.formula(paste("~0 +", paste(colnames(meta), collapse = "+"))), data = meta)
dge    <- DGEList(counts = counts); dge <- dge[filterByExpr(dge, design), , keep.lib.sizes = FALSE]
dge    <- calcNormFactors(dge, method = "TMM")
v      <- voom(dge, design)
fit    <- eBayes(contrasts.fit(lmFit(v, design), makeContrasts(contrasts = args[3], levels = design)))
tt     <- topTable(fit, number = Inf, sort.by = "P", adjust.method = "BH")
write.table(tt, file = args[4], sep = "\t", quote = FALSE, col.names = NA)
