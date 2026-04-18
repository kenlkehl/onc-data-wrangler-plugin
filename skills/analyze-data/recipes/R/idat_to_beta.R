#!/usr/bin/env Rscript
# Usage: Rscript idat_to_beta.R <idat_dir> <sample_sheet.csv> <out_beta.tsv>
# sample_sheet must have columns Sample_Name, Sentrix_ID, Sentrix_Position, Basename (minfi convention).
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
suppressPackageStartupMessages({ library(minfi); library(IlluminaHumanMethylationEPICmanifest) })
targets <- read.metharray.sheet(base = args[1], pattern = basename(args[2]))
rgset   <- read.metharray.exp(targets = targets, force = TRUE)
mset    <- preprocessNoob(rgset)
beta    <- getBeta(mset)
write.table(beta, file = args[3], sep = "\t", quote = FALSE, col.names = NA)
