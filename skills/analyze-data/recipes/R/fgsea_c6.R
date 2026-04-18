#!/usr/bin/env Rscript
# Usage: Rscript fgsea_c6.R <ranked_stats.tsv> <out_fgsea.tsv> [collection]
# ranked_stats.tsv: two columns (gene_symbol, stat); higher stat = more upregulated.
# collection: msigdbr collection + subcollection, default "C6" (oncogenic signatures).
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) >= 2)
suppressPackageStartupMessages({ library(fgsea); library(msigdbr) })
coll   <- if (length(args) >= 3) args[3] else "C6"
r      <- read.table(args[1], sep = "\t", header = TRUE, check.names = FALSE)
stats  <- setNames(r[[2]], r[[1]])
stats  <- stats[!is.na(stats) & !duplicated(names(stats))]
sets   <- split(msigdbr(species = "Homo sapiens", category = coll)$gene_symbol,
                msigdbr(species = "Homo sapiens", category = coll)$gs_name)
set.seed(42)
res    <- fgseaMultilevel(sets, stats, minSize = 15, maxSize = 500, nPermSimple = 10000)
write.table(res[order(res$padj), ], file = args[2], sep = "\t", quote = FALSE, row.names = FALSE)
