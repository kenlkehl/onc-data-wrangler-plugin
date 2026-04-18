#!/usr/bin/env Rscript
# Usage: Rscript consensus_cluster.R <beta.tsv> <k_max> <out_prefix>
# Selects top-N (default 5000) most-variable probes by MAD, runs ConsensusClusterPlus with k=2..k_max,
# writes <out_prefix>_assignments.tsv (sample, cluster_at_k{K}) and <out_prefix>_consensus.rds.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
suppressPackageStartupMessages({ library(ConsensusClusterPlus) })
N     <- 5000
beta  <- as.matrix(read.table(args[1], sep = "\t", header = TRUE, row.names = 1, check.names = FALSE))
mad_v <- apply(beta, 1, mad, na.rm = TRUE)
top   <- beta[order(mad_v, decreasing = TRUE)[seq_len(min(N, length(mad_v)))], ]
set.seed(42)
res   <- ConsensusClusterPlus(top, maxK = as.integer(args[2]), reps = 1000,
                              pItem = 0.8, pFeature = 1, clusterAlg = "hc",
                              distance = "pearson", plot = NULL, seed = 42)
assign <- sapply(2:as.integer(args[2]), function(k) res[[k]]$consensusClass)
colnames(assign) <- paste0("k", 2:as.integer(args[2]))
write.table(assign, file = paste0(args[3], "_assignments.tsv"), sep = "\t", quote = FALSE, col.names = NA)
saveRDS(res, paste0(args[3], "_consensus.rds"))
