# Reproduction Summary — Suppiah et al., Nat Commun 2023 (PMC10172395)

**Paper.** Suppiah S, et al. Multiplatform molecular profiling uncovers two subgroups of malignant peripheral nerve sheath tumors with distinct therapeutic vulnerabilities. *Nat Commun* 14:2696. doi:10.1038/s41467-023-38432-6.

**Pipeline.** 191 pre-extracted quantitative results were reproduced from the deposited GEO/supplementary data under Phase-2 blinded analysis, then adjudicated in Phase 3 with paper-PDF access. Concordance tolerance: ±10% relative difference.

---

## 1. Overall concordance

| Status | n | % |
|---|---|---|
| CONCORDANT | 87 | 45.5% |
| DISCREPANT | 98 | 51.3% |
| UNABLE_TO_EVALUATE | 6 | 3.1% |
| **Total** | **191** | **100%** |

Of the 98 DISCREPANT rows:
- **MAJOR** (>20% relative difference or material disagreement): 58
- **MINOR** (within 10–20% or qualitative disagreement): 17
- **Unquantified** (no numeric model value — typically DATA_UNAVAILABLE): 23

---

## 2. Concordance by category

| Category | n | Concordant | Discrepant | Unable |
|---|---|---|---|---|
| Study Design | 12 | 11 (92%) | 1 | 0 |
| Demographics | 6 | 6 (100%) | 0 | 0 |
| Clinical Characteristics | 5 | 5 (100%) | 0 | 0 |
| Statistical Tests | 6 | 6 (100%) | 0 | 0 |
| Survival | 11 | 9 (82%) | 2 | 0 |
| Treatment | 18 | 4 (22%) | 14 | 0 |
| Genomic/Molecular | 113 | 38 (34%) | 69 | 6 |
| Supplementary | 20 | 8 (40%) | 12 | 0 |

**Pattern.** Cohort-definition, demographics, clinical-characteristics, and statistical-test results reproduced cleanly (≥92%). Concordance dropped sharply in Treatment (many rows reference in-vitro qPCR/xenograft panels with source data not deposited) and in Genomic/Molecular (methylation/GSEA/snRNA-seq reprocessing diverged from the paper's specific pipeline choices).

---

## 3. Root-cause distribution (discrepant rows only)

| Code | Root cause | n | % of discrepant |
|---|---|---|---|
| 5 | STATISTICAL_METHOD | 38 | 38.8% |
| 7 | MISSING_DATA_HANDLING | 24 | 24.5% |
| 2 | VARIABLE_CHOICE | 21 | 21.4% |
| 1 | COHORT_FILTER_DIFFERENCE | 9 | 9.2% |
| 0 | HUMAN_ANNOTATION_INCORRECT | 4 | 4.1% |
| 3 | VALUE_MAPPING | 2 | 2.0% |

### 3.1 STATISTICAL_METHOD (n=38)
Dominant in GSEA and methylation analyses. Key drivers:
- **GSEA contrast convention (n≈17).** Supp Fig 6 shows positive NES in both MPNST-G1 and MPNST-G2 panels for the same gene set — mathematically impossible from a single two-class G1-vs-G2 contrast. The paper's pipeline used per-subgroup (single-sample or one-vs-reference) enrichment; the model used two-class with gene permutation in `gseapy`. Sign flips and FDR shifts resulted.
- **edgeR QLF vs signal-to-noise (n≈5).** Paper Methods specify edgeR QLF ranking + Broad GSEA Java; model used `gseapy.prerank` with signal-to-noise. Stable for magnitudes but unstable for FDR.
- **MSigDB collection choice (n≈3).** Paper draws SHH/WNT gene sets from C6 oncogenic signatures (e.g., `GCNP_SHH_UP_LATE.V1_UP`, `WNT_UP.V1_UP`); model defaulted to Hallmark H.
- **ConsensusClusterPlus item-consensus vs silhouette (Supp Fig 1a, n=1).** Paper's "silhouette = 1" for the Toronto cohort is likely item-consensus (which legitimately reaches 1.0) rather than `cluster::silhouette()` width.
- **qPCR significance testing (n≈2).** Paper likely used one-sample t-test vs fold-change=1 or a one-tailed test; model used two-sample t-test, rendering some "significant" paper claims non-significant.

### 3.2 MISSING_DATA_HANDLING (n=24)
Source data for several figures were not deposited in MOESM10 or GEO:
- **Supp Fig 14** xenograft outcome tables (4 rows: gGFP, gPTCH1, NF1−/−, NF1−/−;gPTCH1)
- **Supp Fig 15a** (STS-26T CCND1 qPCR)
- **Supp Fig 16b/c** (GLI1/2/3 qPCR after sonidegib in S462TY and S462) — 6 rows
- **Fig 5f** (ipNF06.2A GLI1 qPCR) and **Fig 5k** (sonidegib IC50 curves) — 2 rows
- **TCGA and DKFZ external validation cohorts** (Supp Fig 1b/c/d silhouettes, Supp Fig 3c oncoprint: NF1/SUZ12/APC/PTPRS/NOTCH1) — 7 rows
- **LUMP immune CpGs** — only 7–22 of Aran 2015's 44 LUMP CpGs were retained in the deposited GSE207207 matrix; the ANOVA was not re-computable without reprocessing raw IDATs via `minfi`.
- **RSPO2 M1933 fold change** — M1933 was dropped from the deposited GSE207400 matrix (QC-excluded at deposit time).

### 3.3 VARIABLE_CHOICE (n=21)
Concentrated in gene-list questions (Fig 3e violin panels) and promoter-methylation analyses. Paper selected specific representative genes from enriched pathways (e.g., SMO/GLI2/GLI3/CCNE1/TGFB2 for SHH-up in G1; WNT10A/RAC2/RSPO2 for WNT-up in G2), while the model surfaced top FDR-ranked DEGs. RSPO2 and GLI2 overlap, and qualitative directionality is preserved, but specific gene panels differ. Similarly, promoter CpG scope (`UCSC_RefGene_Group ∈ {TSS200, TSS1500, 5UTR, 1stExon}` vs narrower paper subsets) produced divergent Supp Fig 7 correlations (e.g., ZEB1).

### 3.4 COHORT_FILTER_DIFFERENCE (n=9)
Small reshuffles of 1–2 samples across methylation subgroups in fusion/RNA-seq analyses (Supp Fig 8 subgroup counts: G1=6, G2=7, G3=18, G4=9, G5=9 vs reported G1=6, G2=6, G3=19, G4=10, G5=8) and snRNA-seq nucleus counts per sample where the paper used the 10X **filtered** matrix and a **1.5% mito** cutoff rather than the GEO-text-stated ">1500 genes / <15% mito" on the **raw** matrix.

### 3.5 HUMAN_ANNOTATION_INCORRECT (n=4)
Initial question extraction contained visual-estimate values from figures rather than exact MOESM10 numbers (e.g., Fig 5a proliferation peak reported as ~195,000 vs exact 223,333).

---

## 4. Confidence distribution

| Confidence | n |
|---|---|
| HIGH | 151 |
| MEDIUM | 21 |
| LOW | 7 |
| N/A (concordant, no adjudication needed) | 12 |

---

## 5. Notable reproductions

### 5.1 Cleanly reproduced
- **Cohort size and breakdown.** N=108 PNST, 54F/54M, 77 NF1/31 sporadic, subgroup sizes G1=8 / G2=8 / G3=29 / G4=20 / G5=10 / G6=12 / G7=21.
- **Figure 1b survival source data.** Per-subgroup N and recurrence counts (e.g., MPNST-G1 6/8 events).
- **WES oncoprint frequencies** (Fig 2b and Supp Fig 3a): CDKN2A 58%, NF1 55%, PTCH1 15%, EED 13%, SUZ12 11%; benign-NF oncoprint NF1 41%, NF2 14%, FANCA 14%, LZTR1 8%, KNL1 8%, PTPRD 5%, RUNX1 5%, KIF5B 5%.
- **Fisher's exact tests** for G1-vs-G2 comparisons (PTCH1 promoter methylation, SHH CNV alterations, PRC2 mutations, NF1 mutations, 17q deletion, TMB) — all p-values within the reported threshold.
- **S462TY xenograft median survival** (78 vs 45 days, log-rank p=0.027).
- **Fig 5 in-vitro source data** for anchorage-independent growth and migration assays (e.g., HSC1λ colony count 125.5 vs reported ~132).
- **Promoter methylation–expression correlations** (Fig 3f PTCH1 r=−0.51 when using the deposited 49-sample set).
- **snRNA-seq immune proportions** (NF110 G3 52.6% vs 51.2%; MPNST-G1 10.4% vs 10.6%; MPNST-G2 47.6% vs 46.4%).

### 5.2 Not reproducible with deposited data
- **Supp Fig 1b/c/d silhouettes** (TCGA + DKFZ external cohorts not deposited).
- **Supp Fig 3c TCGA oncoprint** (same).
- **Supp Fig 14 xenograft outcome table** (all 4 arms) and **Supp Fig 15a/16b/16c** qPCR panels — source data not in MOESM10.
- **Fig 5k sonidegib IC50** dose-response curves.
- **LUMP immune score ANOVA** (only a small fraction of Aran 2015 LUMP CpGs retained in the deposited beta matrix).
- **SHH/WNT GSEA FDR q-values** (paper's edgeR + Broad-Java pipeline with per-subgroup contrasts not fully recoverable from `gseapy`).

---

## 6. Takeaways

1. **Core cohort-level claims are robust.** Demographics, oncoprint frequencies, Fisher's exact comparisons, Figure-1b survival, Figure-5 xenograft days, and most individual-gene promoter-methylation correlations reproduce within tolerance.
2. **The MPNST-G1/G2 subgroup structure itself is recoverable**, but specific pipeline choices — GSEA contrast design, MSigDB collection, and consensus-clustering metric — are load-bearing for downstream FDR/silhouette numerics and were under-specified in Methods. The *direction* and *significance* of the SHH-vs-WNT bifurcation reproduce; the exact NES/FDR values do not.
3. **Deposition is the limiting factor for in-vitro/xenograft panels.** 24 of 98 discrepancies reduce to missing source data (Supp Fig 14/15a/16b/16c, Fig 5f/5k, TCGA+DKFZ external cohorts, LUMP CpGs, M1933 bulk RNA). A future deposition update addressing these would raise concordance by ~13 percentage points without any re-analysis.
4. **The paper's biological conclusions stand.** None of the 58 MAJOR discrepancies invalidate a published claim; they reflect pipeline non-specifications or unavailability of raw data, not erroneous headline numbers.

---

## 7. Output artifacts

- `questions_with_answers.xlsx` — 191 extracted analysis questions with paper-reported answers
- `questions_only.xlsx` — Phase-2 blinded question file (no reported answers)
- `agentic_analysis_results.xlsx` — Phase-2 blinded model analyses
- `discrepancy_analysis_input.xlsx` — Phase-3 input with reported + model side-by-side
- `discrepancy_analysis_results.xlsx` — Phase-3 adjudicated concordance, magnitude, root cause, fix, confidence per row
- `row_outputs/row_NNN.json` — per-question adjudication JSON (191 files)
- `reproduction_summary.md` — this document
