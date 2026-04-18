#!/usr/bin/env Rscript
# Usage: Rscript conumee_cnv.R <idat_dir> <sample_sheet.csv> <out_cnv_arms.tsv>
# Emits one row per (sample, chromosome_arm) with copy-number log2 ratio and arm-level gain/loss call.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
suppressPackageStartupMessages({ library(minfi); library(conumee); library(IlluminaHumanMethylationEPICmanifest) })
targets <- read.metharray.sheet(base = args[1], pattern = basename(args[2]))
rgset   <- read.metharray.exp(targets = targets, force = TRUE)
mset    <- preprocessIllumina(rgset)
anno    <- CNV.create_anno(array_type = "EPIC")
cnv     <- CNV.load(mset)
out <- do.call(rbind, lapply(names(cnv), function(s) {
  fit <- CNV.fit(cnv[s], CNV.load(mset[, setdiff(colnames(mset), s)]), anno)
  fit <- CNV.bin(CNV.segment(CNV.detail(fit)))
  a   <- CNV.write(fit, what = "segments")
  transform(a, sample = s)
}))
write.table(out, file = args[3], sep = "\t", quote = FALSE, row.names = FALSE)
