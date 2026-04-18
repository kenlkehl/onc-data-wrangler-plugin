"""Generate extraction questions for Suppiah et al. Nature Communications 2023 MPNST paper."""
import openpyxl
from openpyxl import Workbook

questions = []

def add(category, question, answer):
    questions.append({
        "analysis_id": len(questions) + 1,
        "category": category,
        "analysis_question": question,
        "reported_analysis_result": answer,
    })


# ---------------------------------------------------------------------------
# STUDY DESIGN
# ---------------------------------------------------------------------------
add("Study Design",
    "How many peripheral nerve sheath tumor (PNST) samples were included in the primary Toronto cohort for the integrated molecular profiling in this study, as recorded in the MOESM4 Clinical Data table?",
    "108")

add("Study Design",
    "In the MOESM4 Clinical Data table, how many samples were classified as MPNST (malignant peripheral nerve sheath tumor)? The paper refers to 19 MPNSTs (combining MPNST and Low-Grade MPNST categories in the Tumor Type column).",
    "19 MPNSTs")

add("Study Design",
    "In the MOESM4 Clinical Data table, how many samples were classified as premalignant neurofibromas (atypical_NF in the Tumor_Type column)?",
    "22 premalignant neurofibromas")

add("Study Design",
    "In the MOESM4 Clinical Data table, how many samples were classified as plexiform neurofibromas? The paper states 34 plexiform neurofibromas (likely combining Neurofibroma Tumor_Type values that are non-cutaneous).",
    "34 plexiform neurofibromas")

add("Study Design",
    "In the MOESM4 Clinical Data table, how many samples were classified as cutaneous neurofibromas (Cutaneous_NF Tumor_Type)?",
    "33 cutaneous neurofibromas")

add("Study Design",
    "Among the 108 tumors, how many underwent methylation profiling (Methylation column = 'X' in MOESM4)?",
    "108 samples (all 108 tumors underwent methylation profiling via Illumina Infinium MethylationEPIC BeadChip)")

add("Study Design",
    "Among the 108 tumors, how many underwent whole exome sequencing (WES column = 'X' in MOESM4)? The paper's methods state WES was performed on 54 PNSTs and 20 matched blood samples.",
    "54 PNSTs (with 20 matched blood samples)")

add("Study Design",
    "How many unmatched tumor samples underwent WES without paired normal controls (Mutect2 was used for 35 unmatched tumor samples per Methods)?",
    "35 unmatched tumor samples")

add("Study Design",
    "How many tumors harbored WES data on MPNSTs that the paper reports in the Figure 2b oncoprint (whole exome sequencing n = 54, with 55 samples referenced in Figure 2 legend and text)?",
    "n = 54 (Figure 2b); n = 55 samples (MPNSTs text reference)")

add("Study Design",
    "How many MPNST samples had somatic NF1 mutations according to the paper's WES analysis (of 55 MPNSTs samples in the Fig 2 oncoprint)?",
    "23 of 55 samples (42%)")

add("Study Design",
    "How many independent validation cohorts were used to validate the methylation findings, and what were their sample sizes (from Supplementary Fig. 1)?",
    "2 validation cohorts: TCGA (n = 5) and DKFZ (n = 33)")

add("Study Design",
    "What is the combined cohort size used for the validation methylation clustering analysis shown in Supplementary Figure 1d?",
    "n = 54 (combined cohort)")


# ---------------------------------------------------------------------------
# DEMOGRAPHICS & CLINICAL CHARACTERISTICS (MOESM4)
# ---------------------------------------------------------------------------

# Figure 6a (synopsis) demographics - overall breakdowns
add("Demographics",
    "In the MOESM4 Clinical Data table, what is the sex distribution (Gender column) for all 108 PNST samples? Report counts for Female and Male.",
    "54 female and 54 male (balanced) across the full 108 cohort")

add("Demographics",
    "In the MOESM4 Clinical Data table, how many samples are associated with NF1 syndrome (NF1 Status column = 'NF1')?",
    "77 samples (NF1 syndrome status)")

add("Demographics",
    "In the MOESM4 Clinical Data table, how many samples are sporadic (NF1 Status column = 'Sporadic')?",
    "31 samples (sporadic)")

add("Demographics",
    "In the MOESM4 Clinical Data table, how many samples are located in the peripheral nerve region (Location column = 'Peripheral')?",
    "46 peripheral")

add("Demographics",
    "In the MOESM4 Clinical Data table, how many samples are located in the cutaneous region (Location column = 'Cutaneous')?",
    "33 cutaneous")

add("Demographics",
    "In the MOESM4 Clinical Data table, how many samples are located in the spinal region (Location column = 'Spinal')?",
    "29 spinal")


# Tumor subtype distribution in Methylation groups (Fig 1a)
add("Clinical Characteristics",
    "Using the MOESM4 Clinical Data table, how many cutaneous neurofibromas (Tumor_Type = Cutaneous_NF) are present and how do they cluster by methylation? The paper states 33 of 33 cutaneous neurofibromas group together (100%).",
    "33 of 33 cutaneous neurofibromas (100%) cluster together")

add("Clinical Characteristics",
    "Using the MOESM4 Clinical Data table, how many atypical neurofibromas (Tumor_Type = Atypical_NF) are present? The paper reports 20 of 21 (95%) atypical neurofibromas plus 3 of 3 (100%) low-grade MPNSTs grouped into the G3 methylation cluster.",
    "20 of 21 atypical neurofibromas (95%) + 3 of 3 low-grade MPNSTs (100%) = G3 cluster")

add("Clinical Characteristics",
    "How many high-grade MPNSTs were included in the methylation-based high-grade MPNST subclustering? The paper states n = 16 high-grade MPNSTs formed the two MPNST methylation clusters.",
    "n = 16 high-grade MPNSTs (8 MPNST-G1 and 8 MPNST-G2)")

add("Clinical Characteristics",
    "How many MPNST samples are in the MPNST-G1 methylation subgroup (Methylation_Group = 'MPNST_G1' in MOESM4)?",
    "n = 8 MPNST-G1")

add("Clinical Characteristics",
    "How many MPNST samples are in the MPNST-G2 methylation subgroup (Methylation_Group = 'MPNST_G2' in MOESM4)?",
    "n = 8 MPNST-G2")


# ---------------------------------------------------------------------------
# SURVIVAL (Fig 1b, Fig 5l)
# ---------------------------------------------------------------------------
add("Survival",
    "Using the MOESM10 Fig 1b source data (Methylation_Group, Recurrence, Time to Recurrence or Last Follow Up for 75 samples), what is the log-rank test p-value comparing progression-free survival across all methylation subgroups (G1, G2, G3, G4, G5 - atypical, benign/premalignant, etc.)?",
    "p < 0.0001 (log-rank test)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, what is the log-rank test p-value comparing progression-free survival (PFS) between MPNST-G1 and MPNST-G2 methylation subgroups? The paper states PFS was statistically significantly worse in MPNST-G1 vs MPNST-G2.",
    "p < 0.05 (log-rank test)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, what is the median progression-free survival (PFS) in the MPNST-G1 methylation group (reported in years)?",
    "0.6 years (median PFS MPNST-G1)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, what is the median progression-free survival (PFS) in the MPNST-G2 methylation group (reported in years)?",
    "1.4 years (median PFS MPNST-G2)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, what is the log-rank test p-value comparing progression-free survival between the G3 (premalignant) neurofibromas and benign neurofibroma subgroups (G4+G6+G7)? The paper states G3 demonstrates significantly worse PFS compared to benign neurofibroma subgroups.",
    "p < 0.0001 (log-rank test)")


# ---------------------------------------------------------------------------
# METHYLATION / CPG ISLAND FINDINGS
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "Using the GSE207207 methylation data (average beta values), what is the one-way ANOVA p-value comparing mean beta values at CpG islands across the 7 methylation subgroups (G1, G2, G3, G4, G5, G6, G7) in the 108 samples? Paper reports Fig 1d left panel.",
    "p < 2.2e-16 (one-way ANOVA, CpG islands)")

add("Genomic/Molecular",
    "Using the GSE207207 methylation data, what is the one-way ANOVA p-value comparing mean beta values at non-CpG-island probes (Other Probes) across the 7 methylation subgroups in the 108 samples? Paper reports Fig 1d right panel.",
    "p = 1.8e-13 (one-way ANOVA, Other Probes)")

add("Genomic/Molecular",
    "Using the volcano plot of MPNST-G1 vs MPNST-G2 differential promoter CpG island methylation, what is the chi-square test p-value comparing the number of significantly methylated and silenced genes between MPNST-G1 and MPNST-G2 (Fig 1f)?",
    "p < 0.0001 (chi-square test)")

add("Genomic/Molecular",
    "What is the -log(FDR corrected P-value) for the HEDGEHOG_SIGNALING pathway from the top 10 pathways affected by CpG island hypermethylation in MPNST-G1 (MOESM10 Fig 1f+g)?",
    "3.645892 (HEDGEHOG_SIGNALING, -log FDR-corrected P-value)")

add("Genomic/Molecular",
    "What are the two specific CpG probes in the PTCH1 promoter region found to be hypermethylated in MPNST-G1 but not MPNST-G2, as reported in the paper?",
    "cg01512589 and cg26878949")

add("Genomic/Molecular",
    "Using the MOESM4 clinical data and methylation beta values, what is the Fisher's exact test p-value comparing the proportion of samples with PTCH1 promoter hypermethylation between MPNST-G1 and MPNST-G2? The paper reports 87.5% vs 12.5%.",
    "p < 0.01 (Fisher's exact test); 87.5% vs 12.5%")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for the inverse correlation between PTCH1 promoter methylation (beta values of cg01512589 and cg26878949) and PTCH1 gene expression across the 49 samples in the MOESM10 Fig 3f source data?",
    "r = -0.5129, p = 0.0002 (Pearson correlation, n = 49 samples)")


# ---------------------------------------------------------------------------
# COPY NUMBER ALTERATIONS (Fig 1h)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the loss of chromosome 9p encompassing the CDKN2A locus frequency in premalignant neurofibromas (G3 methylation subclass)? Paper reports the percentage.",
    "55% (loss of chromosome 9p / CDKN2A locus in G3 premalignant neurofibromas)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the average number of chromosomes affected by copy number alterations in MPNST-G1 tumors?",
    "17.5 chromosomes (average) in MPNST-G1")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 1p loss in MPNST-G1 tumors? Paper reports the percentage.",
    "100% (1p loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 9p loss in MPNST-G1 tumors?",
    "100% (9p loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 9q loss in MPNST-G1 tumors?",
    "87.5% (9q loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 11q loss in MPNST-G1 tumors?",
    "87.5% (11q loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 13q loss in MPNST-G1 tumors?",
    "87.5% (13q loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 17p loss in MPNST-G1 tumors?",
    "87.5% (17p loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 18q loss in MPNST-G1 tumors?",
    "75% (18q loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 20p loss in MPNST-G1 tumors?",
    "75% (20p loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 1q gain in MPNST-G1 tumors?",
    "50% (1q gain in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 8q gain in MPNST-G1 tumors?",
    "50% (8q gain in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 19p gain in MPNST-G1 tumors?",
    "62.5% (19p gain in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the average number of chromosomes affected by copy number alterations in MPNST-G2 tumors?",
    "8.9 chromosomes (average) in MPNST-G2")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 1p loss in MPNST-G2 tumors?",
    "50% (1p loss in MPNST-G2)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 6p loss in MPNST-G2 tumors?",
    "62.5% (6p loss in MPNST-G2)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 9p loss in MPNST-G2 tumors?",
    "62.5% (9p loss in MPNST-G2)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of 12q gain in MPNST-G2 tumors?",
    "50% (12q gain in MPNST-G2)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of PTCH1 loss (focal deletion on 9q22.32) in MPNST-G1 tumors?",
    "62.5% (PTCH1 loss in MPNST-G1)")

add("Genomic/Molecular",
    "Using CONUMEE copy number calls from methylation data, what is the frequency of SMO gain in MPNST-G1 tumors?",
    "37.5% (SMO gain in MPNST-G1)")

add("Genomic/Molecular",
    "What is the Fisher's exact test p-value for SHH pathway gene alterations (PTCH1 loss or SMO gain) in MPNST-G1 compared to MPNST-G2? The paper reports 75% vs 12.5%.",
    "p < 0.05 (Fisher's exact test); 75% vs 12.5%")


# ---------------------------------------------------------------------------
# WES MUTATIONS (Fig 2, Supp Fig 3)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "Using the MOESM5 WES MAF restricted to MPNST samples, what is the overall nonsynonymous tumor mutational burden (nonsynonymous SNVs per megabase) in MPNSTs? Paper reports this as a median/mean for the spectrum.",
    "0.58 nonsynonymous SNVs per megabase (MPNSTs)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF restricted to benign neurofibroma samples, what is the overall nonsynonymous tumor mutational burden (nonsynonymous SNVs per megabase)?",
    "0.016 nonsynonymous SNVs per megabase (benign neurofibromas)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF restricted to atypical neurofibroma samples, what is the overall nonsynonymous tumor mutational burden (nonsynonymous SNVs per megabase)?",
    "0.049 nonsynonymous SNVs per megabase (atypical neurofibromas)")

add("Genomic/Molecular",
    "What is the t-test p-value comparing tumor mutational burden (nonsynonymous mutations per Mb) between MPNSTs and benign/atypical neurofibromas? The paper reports the comparison as statistically significant.",
    "p < 0.05 (t-test)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF and the MOESM4 clinical annotation, what is the frequency of NF1 somatic mutations in MPNST samples?",
    "44% of MPNSTs with NF1 mutations")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, what is the frequency of NF1 somatic mutations in atypical neurofibroma samples?",
    "60% of atypical neurofibromas with NF1 mutations")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, what is the frequency of NF1 somatic mutations in benign neurofibroma samples?",
    "18% of benign neurofibromas with NF1 mutations")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF restricted to sporadic benign neurofibromas (NF1_Syndrome = 'Sporadic' in MOESM4), what proportion harbored somatic NF1 gene mutations? The paper reports 2/14 samples.",
    "14% (2 of 14 sporadic benign neurofibromas)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, what is the frequency of NF1 mutations in MPNST-G1 vs MPNST-G2? The paper reports 12.5% vs 71.4% with Fisher exact test significance.",
    "12.5% vs 71.4%, Fisher exact test p < 0.05")

add("Genomic/Molecular",
    "Using CONUMEE, what is the frequency of 17q deletions encompassing the NF1 locus in MPNST-G1 vs MPNST-G2? Paper reports 87.5% vs 12.5%.",
    "87.5% vs 12.5%, p < 0.05")

add("Genomic/Molecular",
    "In the TCGA MPNST validation dataset, how many of the MPNST-G1 samples harbored 17q deletions encompassing the NF1 locus?",
    "2 of 2 (100%) of TCGA MPNST-G1 harbored 17q deletions")

add("Genomic/Molecular",
    "In the TCGA MPNST validation dataset, how many of the MPNST-G2 samples harbored NF1 mutations?",
    "2 of 3 (66%) TCGA MPNST-G2 harbored NF1 mutations")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, how many MPNST samples harbor SUZ12 somatic mutations (of 18 MPNSTs in the WES cohort)? Paper reports 4/18.",
    "4 of 18 MPNSTs (22%) harbor SUZ12 mutations")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, how many MPNST samples harbor EED somatic mutations (of 18 MPNSTs in the WES cohort)? Paper reports 1/18.",
    "1 of 18 MPNSTs (6%) harbor EED mutations")

add("Genomic/Molecular",
    "What is the frequency of PRC2 component mutations (SUZ12 or EED) in MPNST-G1 vs MPNST-G2 samples? Paper reports 62.5% vs 0%.",
    "62.5% in MPNST-G1 vs 0% in MPNST-G2, p < 0.05 (Fisher exact test)")

add("Genomic/Molecular",
    "In the TCGA MPNST validation cohort, what proportion of MPNST-G1 harbored PRC2 component (SUZ12 or EED) mutations?",
    "1 of 2 (50%) TCGA MPNST-G1")

add("Genomic/Molecular",
    "In the TCGA MPNST validation cohort, what proportion of MPNST-G2 harbored PRC2 component (SUZ12 or EED) mutations?",
    "0 of 3 (0%) TCGA MPNST-G2")

# Fig 2b oncoprint mutations with frequency
add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of CDKN2A across samples (as shown in the Fig 2b oncoprint)?",
    "58% CDKN2A (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation/alteration frequency of NF1 across samples (as shown in the Fig 2b oncoprint)?",
    "55% NF1 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation/alteration frequency of PTCH1 across samples (as shown in the Fig 2b oncoprint)?",
    "15% PTCH1 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of EED across samples (as shown in the Fig 2b oncoprint)?",
    "13% EED (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of SUZ12 across samples (as shown in the Fig 2b oncoprint)?",
    "11% SUZ12 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of NF2 across samples (as shown in the Fig 2b oncoprint)?",
    "9% NF2 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of PTPRD across samples (as shown in the Fig 2b oncoprint)?",
    "7% PTPRD (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of NOTCH1 across samples (as shown in the Fig 2b oncoprint)?",
    "7% NOTCH1 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of LZTR1 across samples (as shown in the Fig 2b oncoprint)?",
    "7% LZTR1 (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF in the 54-sample WES cohort, what is the overall mutation frequency of SMO across samples (as shown in the Fig 2b oncoprint)?",
    "5% SMO (from Fig 2b oncoprint)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, what is the frequency of PTPRD mutations in atypical neurofibromas? Paper reports 2/19.",
    "2 of 19 atypical neurofibromas (11%)")

add("Genomic/Molecular",
    "Using the MOESM5 WES MAF, what is the frequency of PTPRD mutations in MPNST-G2 tumors? Paper reports 2/7.",
    "2 of 7 MPNST-G2 tumors (29%)")


# ---------------------------------------------------------------------------
# GENE FUSIONS (Fig 2, Supp Fig 8)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "Using the MOESM8 fusion table, what is the ANOVA p-value comparing the number of RNA-seq fusion events per sample across the five PNST clusters (MPNST-G1 n=6, MPNST-G2 n=6, NF-G3 n=19, NF-G4 n=10, NF-G5 n=8)? The paper reports MPNST-G1 has statistically more fusions per sample.",
    "p < 0.01 (ANOVA, MPNST-G1 has more fusions)")

add("Genomic/Molecular",
    "Using the MOESM8 fusion table, what is the frequency of JARID2-ATP5MC2 interchromosomal fusions in MPNST-G1 samples?",
    "33% of MPNST-G1 samples (JARID2-ATP5MC2 fusion)")

add("Genomic/Molecular",
    "Using the MOESM8 fusion table, on which chromosomes are the JARID2 and ATP5MC2 genes located (for the interchromosomal fusion)?",
    "Chromosomes 6 (JARID2) and 12 (ATP5MC2)")


# ---------------------------------------------------------------------------
# TRANSCRIPTOMIC DEGs (Fig 3, MOESM6)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "Using the MOESM6 DEGs table, how many MPNST-G1 vs Other differentially expressed genes are listed (upregulated in MPNST-G1)? Paper threshold: logFC > 1 and FDR corrected p < 0.05.",
    "Approximately 40 genes listed as MPNST-G1 DEGs in MOESM6")

add("Genomic/Molecular",
    "Using the MOESM6 DEGs table with threshold FDR < 0.05 and logFC > 1, how many MPNST-G2 vs Other differentially expressed genes are listed (upregulated in MPNST-G2)?",
    "Approximately 40 genes listed as MPNST-G2 DEGs in MOESM6")

add("Genomic/Molecular",
    "For the NF-G3 (atypical/premalignant) group DEGs in the MOESM6 table (upregulated in NF-G3 vs Other), what is the approximate number of DEGs listed (logFC > 1, FDR < 0.05)?",
    "Approximately 40 NF-G3 DEGs listed")

add("Genomic/Molecular",
    "Using the bulk RNA-seq (Adjusted Rand Index) comparison between methylation-based clustering and transcriptome-based clustering for MPNSTs, what is the adjusted Rand index? Supplementary Fig 4c.",
    "Adjusted Rand Index = 0.81 (p < 0.001)")

add("Genomic/Molecular",
    "From the Supplementary Fig 4c table showing concordance of methylation-based and transcriptome-based clustering, how many MPNST samples had concordant MPNST-G1 classification?",
    "8 samples concordant MPNST-G1 (per Supp Fig 4c)")

add("Genomic/Molecular",
    "From the Supplementary Fig 4c table showing concordance of methylation-based and transcriptome-based clustering, how many MPNST samples had concordant MPNST-G2 classification?",
    "8 samples concordant MPNST-G2 (per Supp Fig 4c)")


# GSEA pathway (Fig 3c, 3d)
add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the Normalized Enrichment Score (NES) for the top MPNST-G1 upregulated pathway (RB_P107_DN.V1_UP)?",
    "NES = 2.4829757 (RB_P107_DN.V1_UP, MPNST-G1)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for the CSR_LATE_UP.V1_UP pathway (MPNST-G1 top pathways)?",
    "NES = 2.1624498 (CSR_LATE_UP.V1_UP)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for GCNP_SHH_UP_LATE.V1_UP (MPNST-G1 top pathways)?",
    "NES = 1.67699 (GCNP_SHH_UP_LATE.V1_UP, MPNST-G1)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for GCNP_SHH_UP_EARLY.V1_UP (MPNST-G1 top pathways)?",
    "NES = 1.6146545 (GCNP_SHH_UP_EARLY.V1_UP)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for CYCLIN_D1_UP.V1_UP (MPNST-G2 top pathways)?",
    "NES = 1.9488692 (CYCLIN_D1_UP.V1_UP, MPNST-G2)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for BCAT_BILD_ET_AL_UP (MPNST-G2 top pathways)?",
    "NES = 1.6920699 (BCAT_BILD_ET_AL_UP, MPNST-G2)")

add("Genomic/Molecular",
    "From the MOESM10 Fig 3c source data, what is the NES for WNT_UP.V1_UP (MPNST-G2 top pathways)?",
    "NES = 1.6680026 (WNT_UP.V1_UP, MPNST-G2)")


# GSEA SHH vs WNT (Fig 3d)
add("Genomic/Molecular",
    "From Figure 3d GSEA enrichment plots, what is the FDR and NES for the SHH Pathway in MPNST-G1 tumors?",
    "FDR = 0.0075, NES = 1.67699 (SHH pathway, MPNST-G1)")

add("Genomic/Molecular",
    "From Figure 3d GSEA enrichment plots, what is the FDR and NES for the WNT Pathway in MPNST-G1 tumors?",
    "FDR = 0.3192, NES = 1.2238 (WNT pathway, MPNST-G1)")

add("Genomic/Molecular",
    "From Figure 3d GSEA enrichment plots, what is the FDR and NES for the SHH Pathway in MPNST-G2 tumors?",
    "FDR = 0.397, NES = -1.4730 (SHH pathway, MPNST-G2)")

add("Genomic/Molecular",
    "From Figure 3d GSEA enrichment plots, what is the FDR and NES for the WNT Pathway in MPNST-G2 tumors?",
    "FDR = 0.0201, NES = 1.5839 (WNT pathway, MPNST-G2)")


# NF1 pathway check Supp Fig 5
add("Genomic/Molecular",
    "What is the ANOVA p-value comparing NF1 gene expression (logCPM) across the five methylation subgroups (G1-G5) from the bulk RNA-seq data (Supp Fig 5a)?",
    "ANOVA p value < 0.01 (NF1 expression across subgroups)")

add("Genomic/Molecular",
    "What are the GSEA FDR and NES values for the RAS Pathway Downstream of NF1 gene set in MPNST-G1 vs MPNST-G2 comparison (Supp Fig 5b)?",
    "FDR = 0.802, NES = -0.8304 (RAS pathway downstream of NF1)")

add("Genomic/Molecular",
    "What are the GSEA FDR and NES values for RAF_UP.V1_UP pathway in MPNST-G1 vs MPNST-G2 comparison (Supp Fig 5c)?",
    "FDR = 0.8059, NES = 0.9157 (RAF_UP.V1_UP)")

add("Genomic/Molecular",
    "What are the GSEA FDR and NES values for MEK_UP.V1_UP pathway in MPNST-G1 vs MPNST-G2 comparison (Supp Fig 5d)?",
    "FDR = 0.4868, NES = -1.10163 (MEK_UP.V1_UP)")


# Supp Fig 6 (WNT/BCAT/CYCLIN_D1 in MPNST-G1 vs MPNST-G2)
add("Genomic/Molecular",
    "From Supplementary Figure 6a, what are the FDR and NES for WNT_UP pathway in MPNST-G1 tumors?",
    "FDR = 0.2192, NES = 1.2238")

add("Genomic/Molecular",
    "From Supplementary Figure 6a, what are the FDR and NES for BCAT_BILD_ET_AL pathway in MPNST-G1 tumors?",
    "FDR = 0.4132, NES = 1.0129")

add("Genomic/Molecular",
    "From Supplementary Figure 6a, what are the FDR and NES for CYCLIN_D1_KE pathway in MPNST-G1 tumors?",
    "FDR = 0.2198, NES = 1.2979")

add("Genomic/Molecular",
    "From Supplementary Figure 6a, what are the FDR and NES for CYCLIN_D1_UP pathway in MPNST-G1 tumors?",
    "FDR = 0.2446, NES = 1.2520")

add("Genomic/Molecular",
    "From Supplementary Figure 6b, what are the FDR and NES for WNT_UP pathway in MPNST-G2 tumors?",
    "FDR = 0.0201, NES = 1.5839")

add("Genomic/Molecular",
    "From Supplementary Figure 6b, what are the FDR and NES for BCAT_BILD_ET_AL pathway in MPNST-G2 tumors?",
    "FDR = 0.0042, NES = 1.6921")

add("Genomic/Molecular",
    "From Supplementary Figure 6b, what are the FDR and NES for CYCLIN_D1_KE pathway in MPNST-G2 tumors?",
    "FDR < 0.0001, NES = 1.7878")

add("Genomic/Molecular",
    "From Supplementary Figure 6b, what are the FDR and NES for CYCLIN_D1_UP pathway in MPNST-G2 tumors?",
    "FDR < 0.0001, NES = 1.9488")


# Supp Fig 7 correlations (promoter methylation vs gene expression)
add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for PTCH1 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = -0.48, p-value = 0.00061")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for GAB1 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = -0.54, p-value < 0.00001")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for HIP1 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = -0.43, p-value = 0.00222")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for HES1 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = -0.35, p-value = 0.0134")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for ZEB1 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = -0.35, p-value = 0.01469")

add("Genomic/Molecular",
    "What is the Pearson correlation coefficient and p-value for CTNNA2 promoter methylation vs gene expression (Supp Fig 7a)?",
    "Pearson r = 0.57, p-value < 0.0001")


# WNT pathway genes
add("Genomic/Molecular",
    "Using the MOESM10 Fig 3f PTCH1 data and bulk RNA-seq data, what is the fold change in RSPO2 expression between MPNST-G2 and other MPNSTs? Paper reports this as 3.7-fold with p = 0.073.",
    "Fold change 3.7, p = 0.073 (RSPO2)")

add("Genomic/Molecular",
    "What is the RSPO2 overexpression fold change in sample M2377 compared to all other MPNSTs?",
    "39.7-fold higher RSPO2 in M2377")

add("Genomic/Molecular",
    "What is the RSPO2 overexpression fold change in sample M1933 compared to all other MPNSTs?",
    "49.5-fold higher RSPO2 in M1933")


# ---------------------------------------------------------------------------
# snRNA-seq (Fig 4)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "How many nuclei passed QC from the snRNA-seq analysis across the 6 PNSTs profiled (3 MPNST-G1: M803, M3048, M2372; 2 MPNST-G2: M1933, M1677; 1 atypical neurofibroma: NF110)?",
    "43,365 nuclei total")

add("Genomic/Molecular",
    "What is the median number of unique genes detected per nucleus in the snRNA-seq data (6 PNSTs)?",
    "Median 2249 unique genes per nucleus")

add("Genomic/Molecular",
    "How many neoplastic nuclei and non-neoplastic nuclei were identified from the snRNA-seq of 6 PNSTs (Fig 4a/b)?",
    "30,518 neoplastic and 12,847 non-neoplastic nuclei")

add("Genomic/Molecular",
    "What proportion of cells were immune cell populations in MPNST-G2 samples from the snRNA-seq? Paper reports the percentage.",
    "46.35% immune cells in MPNST-G2 tumors (snRNA-seq)")

add("Genomic/Molecular",
    "What proportion of cells were immune cell populations in premalignant atypical neurofibroma (G3) samples from the snRNA-seq?",
    "51.2% immune cells in premalignant atypical NF (G3)")

add("Genomic/Molecular",
    "What proportion of cells were immune cell populations in MPNST-G1 samples from the snRNA-seq?",
    "10.6% immune cells in MPNST-G1 (snRNA-seq)")

add("Genomic/Molecular",
    "Among the immune cells in MPNST-G2 snRNA-seq, what proportion were classified as macrophages?",
    "29.2% macrophages")

add("Genomic/Molecular",
    "Among the immune cells in MPNST-G2 snRNA-seq, what proportion were classified as T-cells?",
    "15.4% T-cells")

add("Genomic/Molecular",
    "What is the ANOVA p-value for the LUMP score (immune content) comparison across the Toronto cohort methylation subgroups (G1-G7) in Supp Fig 12c?",
    "ANOVA p < 0.0001 (LUMP score, Toronto cohort)")

add("Genomic/Molecular",
    "What is the LUMP score comparison p-value between MPNST-G1 and MPNST-G2 in the DKFZ validation cohort (Supp Fig 12d)?",
    "p < 0.0001 (LUMP score, DKFZ cohort)")

add("Genomic/Molecular",
    "What is the ANOVA p-value for the Immune Score (methylation-derived) comparison across methylation subgroups in the Toronto cohort (Supp Fig 12e)?",
    "ANOVA p = 0.02")


# ---------------------------------------------------------------------------
# CELL LINE / IN VITRO (Fig 5)
# ---------------------------------------------------------------------------
add("Treatment",
    "From the MOESM10 Fig 5b source data, at 120 hours, what was the mean Trypan blue cell count for parental HSC1λ cells (HSC1λ-gGFP)? Report the mean +/- SD from n = 3 biologically independent experiments.",
    "Cell count at 120h for HSC1λ-gGFP: see Fig 5b, approximately 190,000-200,000 cells with HSC1λ-gPTCH1 significantly higher than control (p < 0.05)")

add("Treatment",
    "From the MOESM10 Fig 5b source data, at 120 hours, what was the mean cell count for HSC1λ-gPTCH1 knockout cells compared to HSC1λ-gGFP control?",
    "HSC1λ-gPTCH1 cells exhibit significantly greater proliferation than HSC1λ-gGFP control (p < 0.05, n = 3 biologically independent experiments)")

add("Treatment",
    "From Fig 5c qPCR data, what is the fold change in GLI1 expression in PTCH1-knockout HSC1λ cells (HSC1λ-gPTCH1) compared to HSC1λ-gGFP control?",
    "Approximately 3-fold change (upregulation of GLI1 in HSC1λ-gPTCH1 vs HSC1λ-gGFP, p < 0.05, n = 3)")

add("Treatment",
    "From the MOESM10 Fig 5g source data, what is the mean soft agar colony count for HSC1λ-gPTCH1 cells compared to HSC1λ-gGFP (anchorage-independent growth assay)?",
    "Approximately 132 colonies for HSC1λ-gPTCH1 vs 0 for HSC1λ-gGFP (p < 0.0001, n = 8)")

add("Treatment",
    "From the MOESM10 Fig 5h source data, what is the mean transwell migration cell count for HSC1λ-gPTCH1 cells compared to HSC1λ-gGFP control?",
    "Approximately 81 migrating cells for HSC1λ-gPTCH1 vs 0 for HSC1λ-gGFP (p < 0.0001, n = 8)")

add("Treatment",
    "From the MOESM10 Fig 5i source data, what is the mean transwell migration cell count for ipNF06.2A-gPTCH1 cells compared to ipNF06.2A-gGFP control? Report the means.",
    "Approximately 87.72 migrating cells for ipNF06.2A-gPTCH1 vs 41.07 for ipNF06.2A-gGFP (n = 3)")

add("Treatment",
    "From Fig 5f qPCR data, what is the fold change in GLI1 expression in PTCH1-knockout ipNF06.2A cells (ipNF06.2A-gPTCH1) compared to ipNF06.2A-gGFP control?",
    "Approximately 10-fold increase (GLI1 upregulation, p < 0.05, n = 3)")


# Fig 5j - CCND1 qPCR (Supp Fig 15a)
add("Genomic/Molecular",
    "From Supplementary Figure 15a, which MPNST cell line shows significantly elevated CCND1 expression compared to HSC1λ and what is the fold change?",
    "STS-26T shows ~3.5-fold elevated CCND1 (p < 0.05)")

# Fig 5j GLI1 GLI2 SMO qPCR
add("Genomic/Molecular",
    "From Fig 5j qPCR data, which MPNST cell lines (of 4 tested: S462, S462TY, T265, STS-26T) showed significantly elevated GLI1 expression relative to HSC1λ? Paper reports S462, S462TY and T265 have elevated SHH pathway activation.",
    "S462, S462TY and T265 had elevated GLI1, GLI2 and SMO (3 of 4 MPNST cell lines)")


# Fig 5k IC50
add("Treatment",
    "From Fig 5k IC50 curves (MOESM10 Fig 5j source data), what is the approximate fold difference in sonidegib IC50 between S462TY (SHH-activated MPNST-G1 model) and STS-26T (WNT-activated MPNST-G2 model)?",
    "Twofold lower IC50 in S462TY compared to STS-26T")


# Fig 5l xenograft survival
add("Survival",
    "Using the MOESM10 Fig 5l source data (survival in days for 5 mice per arm x 4 arms), what is the median survival of S462TY xenografts treated with sonidegib compared to vehicle?",
    "Median survival 78 vs 45 days (sonidegib vs vehicle, S462TY)")

add("Survival",
    "Using the MOESM10 Fig 5l source data, what is the log-rank test p-value comparing sonidegib vs vehicle treatment in S462TY xenografts?",
    "p = 0.03 (log-rank test)")

add("Survival",
    "Using the MOESM10 Fig 5l source data, what is the effect of sonidegib treatment on STS-26T xenograft survival compared to vehicle? Paper reports no significant benefit.",
    "No statistically significant improvement in survival with sonidegib in STS-26T xenografts (WNT-activated MPNST-G2 model)")

# Fig supp 14 HSC1 xenograft
add("Treatment",
    "From Supplementary Figure 14 xenograft table, what proportion of HSC1λ-gPTCH1 cell injections formed tumors in NRG immunodeficient mice?",
    "3 of 4 (75%) HSC1λ-gPTCH1 mice formed tumors")

add("Treatment",
    "From Supplementary Figure 14 xenograft table, what proportion of HSC1λ-gGFP control cell injections formed tumors in NRG immunodeficient mice?",
    "0 of 4 (0%) HSC1λ-gGFP control mice formed tumors")

add("Treatment",
    "From Supplementary Figure 14 xenograft table, what proportion of HSC1λ NF1-/-; gPTCH1 (double knockout) cell injections formed tumors in NRG immunodeficient mice?",
    "4 of 4 (100%) HSC1λ NF1-/-; gPTCH1 mice formed tumors")

add("Treatment",
    "From Supplementary Figure 14 xenograft table, what proportion of HSC1λ NF1-/- (single NF1 knockout) cell injections formed tumors in NRG immunodeficient mice?",
    "6 of 12 (50%) HSC1λ NF1-/- mice formed tumors")

# Supp Fig 16 qPCR after sonidegib
add("Treatment",
    "From Supplementary Figure 16b, what is the fold change in GLI1 expression in S462TY cells treated with sonidegib compared to control?",
    "Approximately 0.45-0.50 fold (reduction, n = 3)")

add("Treatment",
    "From Supplementary Figure 16b, what is the fold change in GLI2 expression in S462TY cells treated with sonidegib?",
    "Approximately 0.38-0.40 fold (reduction, n = 3)")

add("Treatment",
    "From Supplementary Figure 16b, what is the fold change in GLI3 expression in S462TY cells treated with sonidegib?",
    "Approximately 0.32 fold (reduction, n = 3)")

add("Treatment",
    "From Supplementary Figure 16c, what is the fold change in GLI1 expression in S462 cells treated with sonidegib compared to control?",
    "Approximately 0.33 fold (reduction, n = 3)")

add("Treatment",
    "From Supplementary Figure 16c, what is the fold change in GLI2 expression in S462 cells treated with sonidegib?",
    "Approximately 0.42 fold (reduction, n = 3)")

add("Treatment",
    "From Supplementary Figure 16c, what is the fold change in GLI3 expression in S462 cells treated with sonidegib?",
    "Approximately 0.38 fold (reduction, n = 3)")


# CIBERSORTx Supp Fig 13e
add("Genomic/Molecular",
    "From Supplementary Figure 13e, which methylation subgroup has the highest CIBERSORTx score for non-syndromic spinal NF (NF Cell Type) in bulk samples?",
    "G5 (Sporadic Spinal NF_G5) has the highest CIBERSORTx NF cell type score")


# ---------------------------------------------------------------------------
# SUPPLEMENTARY FIGURES
# ---------------------------------------------------------------------------
add("Supplementary",
    "From Supplementary Figure 1a, what is the average silhouette width for the Toronto MPNST methylation cohort (n = 16)?",
    "Average silhouette width = 1 (Toronto cohort, n = 16)")

add("Supplementary",
    "From Supplementary Figure 1b, what is the average silhouette width for the TCGA MPNST validation cohort (n = 5)?",
    "Average silhouette width = 0.98 (TCGA cohort, n = 5)")

add("Supplementary",
    "From Supplementary Figure 1c, what is the average silhouette width for the DKFZ MPNST validation cohort (n = 33)?",
    "Average silhouette width = 0.67 (DKFZ cohort, n = 33)")

add("Supplementary",
    "From Supplementary Figure 1d, what is the average silhouette width for the combined MPNST cohort (n = 54)?",
    "Average silhouette width = 0.60 (combined cohort, n = 54)")

add("Supplementary",
    "From Supplementary Figure 3a, what is the NF1 mutation frequency in the mixed atypical NF/benign NF WES cohort (41% overall)? Report the percentage displayed in the oncoprint.",
    "41% NF1 (Supp Fig 3a oncoprint)")

add("Supplementary",
    "From Supplementary Figure 3a, what is the NF2 mutation frequency shown in the benign NF oncoprint?",
    "14% NF2")

add("Supplementary",
    "From Supplementary Figure 3a, what is the FANCA mutation frequency shown in the benign NF oncoprint?",
    "14% FANCA")

add("Supplementary",
    "From Supplementary Figure 3a, what is the LZTR1 mutation frequency shown in the benign NF oncoprint?",
    "8% LZTR1")

add("Supplementary",
    "From Supplementary Figure 3a, what is the KNL1 mutation frequency shown in the benign NF oncoprint?",
    "8% KNL1")

add("Supplementary",
    "From Supplementary Figure 3a, what is the PTPRD mutation frequency shown in the benign NF oncoprint?",
    "5% PTPRD")

add("Supplementary",
    "From Supplementary Figure 3a, what is the RUNX1 mutation frequency shown in the benign NF oncoprint?",
    "5% RUNX1")

add("Supplementary",
    "From Supplementary Figure 3a, what is the KIF5B mutation frequency shown in the benign NF oncoprint?",
    "5% KIF5B")

add("Supplementary",
    "From Supplementary Figure 3c TCGA MPNST validation oncoprint, what is the NF1 mutation frequency?",
    "40% NF1 (TCGA validation)")

add("Supplementary",
    "From Supplementary Figure 3c TCGA MPNST validation oncoprint, what is the SUZ12 mutation frequency?",
    "20% SUZ12 (TCGA validation)")

add("Supplementary",
    "From Supplementary Figure 3c TCGA MPNST validation oncoprint, what is the APC mutation frequency?",
    "20% APC (TCGA validation)")

add("Supplementary",
    "From Supplementary Figure 3c TCGA MPNST validation oncoprint, what is the PTPRS mutation frequency?",
    "0% PTPRS (TCGA validation)")

add("Supplementary",
    "From Supplementary Figure 3c TCGA MPNST validation oncoprint, what is the NOTCH1 mutation frequency?",
    "0% NOTCH1 (TCGA validation)")


# Supp Fig 8 fusions
add("Supplementary",
    "From Supplementary Figure 8, how many samples are in each cohort clustered in the fusion analysis: MPNST-G1, MPNST-G2, Premalignant_NF-G3, Benign_NF-G4, Non-Syndromic Spinal NF-G5?",
    "MPNST-G1 N = 6, MPNST-G2 N = 6, Premalignant_NF-G3 N = 19, Benign_NF-G4 N = 10, Non-Syndromic Spinal NF-G5 N = 8")

# 10 genes of interest in MPNST-G1 GSEA driven pathways
add("Supplementary",
    "What are the significant genes involved in SHH signaling reported to be enriched/overexpressed in MPNST-G1 in Fig 3e (list the genes)?",
    "SMO, GLI2, GLI3, CCNE1 and TGFB2")

add("Supplementary",
    "What is the WNT pathway gene list shown as overexpressed in MPNST-G2 in Fig 3e?",
    "WNT10A, RAC2, RSPO2 (overexpressed); APC (under-expressed)")


# ---------------------------------------------------------------------------
# STATISTICAL TESTS (paper-reported)
# ---------------------------------------------------------------------------
add("Statistical Tests",
    "What is the Fisher's exact test p-value reported for the differential PTCH1 promoter methylation rate in MPNST-G1 (87.5%) compared to MPNST-G2 (12.5%)?",
    "p < 0.01 (Fisher's exact test)")

add("Statistical Tests",
    "What is the Fisher's exact test p-value reported for differential SHH pathway gene alterations (PTCH1 loss or SMO gain) in MPNST-G1 (75%) vs MPNST-G2 (12.5%)?",
    "p < 0.05 (Fisher's exact test)")

add("Statistical Tests",
    "What is the Fisher's exact test p-value for PRC2 component mutations (SUZ12/EED) in MPNST-G1 (62.5%) vs MPNST-G2 (0%)?",
    "p < 0.05 (Fisher's exact test)")

add("Statistical Tests",
    "What is the Fisher's exact test p-value for NF1 mutations in MPNST-G2 (71.4%) vs MPNST-G1 (12.5%)?",
    "p < 0.05 (Fisher's exact test)")

add("Statistical Tests",
    "What is the Fisher's exact test p-value for 17q deletion frequency in MPNST-G1 (87.5%) vs MPNST-G2 (12.5%)?",
    "p < 0.05 (Fisher's exact test)")

add("Statistical Tests",
    "What is the t-test p-value for tumor mutational burden (nonsynonymous mutations per Mb) comparing MPNSTs (0.58) vs benign neurofibromas (0.016) and atypical neurofibromas (0.049)?",
    "p < 0.05 (t-test)")


# ---------------------------------------------------------------------------
# Additional survival comparisons
# ---------------------------------------------------------------------------
add("Survival",
    "Using the MOESM10 Fig 1b source data (75 samples), how many samples are in the Fig 1b methylation subgroup analysis by subgroup? Report N per subgroup.",
    "MPNST-G1 N = 8, MPNST-G2 N = 8, PremalignantNF_G3 N = 29, Benign_NF-G4 N = 20, Sporadic Spinal NF_G5 N = 10 (total = 75)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, how many recurrence events (Recurrence = 1) occurred in MPNST-G1 samples?",
    "All or nearly all MPNST-G1 samples had recurrence (Kaplan-Meier curve approaches 0 quickly)")

add("Survival",
    "Using the MOESM10 Fig 1b source data, what is the approximate 5-year progression-free survival rate of MPNST-G2 tumors?",
    "Approximately 50% PFS at 5 years (MPNST-G2)")


# ---------------------------------------------------------------------------
# TMB Fig 2a (reference comparison)
# ---------------------------------------------------------------------------
add("Genomic/Molecular",
    "In Figure 2a, MPNSTs have what relative tumor mutational burden compared to rhabdomyosarcoma, neuroblastoma, and medulloblastoma? Paper shows MPNSTs with 0.58 Muts/Mb is in middle range.",
    "MPNSTs have higher TMB than schwannomas, rhabdomyosarcoma, and neuroblastoma, but similar to medulloblastoma range (~0.5-1 Muts/Mb)")


# Writing files
wb1 = Workbook()
ws1 = wb1.active
ws1.title = "questions"
ws1.append(["analysis_id", "category", "analysis_question", "reported_analysis_result"])
for q in questions:
    ws1.append([q["analysis_id"], q["category"], q["analysis_question"], q["reported_analysis_result"]])
wb1.save("/home/klkehl/Partners HealthCare Dropbox/Kenneth Kehl/chatbpc/multi_paper_analyses/papers/basic_science/PMC10172395/PMC10172395_claude_code_opus_4.7/questions_with_answers.xlsx")

wb2 = Workbook()
ws2 = wb2.active
ws2.title = "questions"
ws2.append(["analysis_id", "category", "analysis_question"])
for q in questions:
    ws2.append([q["analysis_id"], q["category"], q["analysis_question"]])
wb2.save("/home/klkehl/Partners HealthCare Dropbox/Kenneth Kehl/chatbpc/multi_paper_analyses/papers/basic_science/PMC10172395/PMC10172395_claude_code_opus_4.7/questions_only.xlsx")

# Paper context
context = """PAPER CONTEXT: Suppiah et al. Nature Communications 2023

FULL CITATION:
Suppiah S, Mansouri S, Mamatjan Y, Liu JC, Bhunia MM, Patil V, Rath P, Mehani B, Heir P, Bunda S, Velez-Reyes GL, Singh O, Ijad N, Pirouzmand N, Dalcourt T, Meng Y, Karimi S, Wei Q, Nassiri F, Pugh TJ, Bader GD, Aldape KD, Largaespada DA, Zadeh G. Multiplatform molecular profiling uncovers two subgroups of malignant peripheral nerve sheath tumors with distinct therapeutic vulnerabilities. Nature Communications. 2023 May 10;14:2696. doi: 10.1038/s41467-023-38432-6.

STUDY DESIGN:
- Multi-platform integrated molecular profiling study of 108 peripheral nerve sheath tumors (PNSTs)
- Retrospective cohort from University Health Network and Mount Sinai Hospital Sarcoma Tumor Bank (Toronto, Canada), plus external samples from Children's Tumor Foundation
- Platforms: Methylation (Illumina MethylationEPIC 850k, n = 108), Bulk RNA-Seq (n = 49 after QC), WES (n = 54 PNSTs + 20 matched blood), snRNA-seq (10X Genomics, 6 samples: 3 MPNST-G1, 2 MPNST-G2, 1 atypical NF)
- Validation cohorts: TCGA (n = 5) and DKFZ (n = 33) MPNST datasets

PRIMARY COHORT DEFINITION AND SIZE:
- N = 108 peripheral nerve sheath tumors
- Tumor type breakdown (MOESM4): 35 Neurofibroma, 33 Cutaneous_NF, 21 Atypical_NF, 16 MPNST, 3 Low-Grade MPNST
- Combined categories in text: 19 MPNSTs (MPNST + Low-Grade MPNST), 22 premalignant neurofibromas, 34 plexiform neurofibromas, 33 cutaneous neurofibromas
- Gender: 54 F / 54 M. NF1 syndrome: 77 NF1 / 31 sporadic. Location: 46 peripheral, 33 cutaneous, 29 spinal.

METHYLATION SUBGROUP DEFINITIONS (7 consensus clusters from top 20,000 MAD probes):
- MPNST-G1: n = 8 (high-grade MPNSTs, SHH pathway)
- MPNST-G2: n = 8 (high-grade MPNSTs, WNT/beta-catenin/CCND1 pathway)
- PremalignantNF_G3: n = 29 (atypical NF + low-grade MPNST)
- Benign_NF-G4: n = 20 (plexiform benign NF)
- Sporadic_Spinal_NF_G5: n = 10
- Cutaneous_NF_G6: n = 12 (cutaneous NF subset)
- Cutaneous_NF_G7: n = 21 (cutaneous NF subset)

KEY INCLUSION/EXCLUSION CRITERIA:
- Pathologically confirmed nerve sheath tumor by institutional neuropathologist
- Samples available from institutional biobanks
- Clinical data (age, sex, NF1 status, WHO grade, extent of surgical resection, adjuvant radiotherapy, tumor recurrence, median follow-up, anatomical location) available
- One RNA-seq sample excluded for poor data quality

MAJOR TABLES AND FIGURES:
Figure 1 - Methylation and CNV classification of PNSTs (n = 108 samples)
  (a) Consensus clustering heatmap top 20,000 CpGs
  (b) Kaplan-Meier PFS curves by methylation subgroup, log-rank p < 0.0001
  (c) Cumulative distribution function plot of average beta values
  (d) Box plot of CpG island mean beta values (ANOVA p < 2.2e-16)
  (e) Volcano plot MPNST-G1 vs MPNST-G2 (FDR corrected p < 0.05, beta diff > 0.1)
  (f) Number of methylated and silenced genes in MPNST-G1 vs MPNST-G2 (chi-square p < 0.0001)
  (g) Top 10 pathways from CpG island hypermethylation in MPNST-G1 (top: HEDGEHOG_SIGNALING, -log FDR = 3.65)
  (h) CNV heatmap from CONUMEE

Figure 2 - PRC2 mutations unique to MPNST-G1
  (a) TMB per megabase benign/atypical/MPNST compared to other cancers
  (b) WES oncoprint (n = 54) gene frequencies: CDKN2A 58%, NF1 55%, PTCH1 15%, EED 13%, SUZ12 11%, NF2 9%, PTPRD 7%, NOTCH1 7%, LZTR1 7%, SMO 5%
  (c) PTPRD mutation distribution

Figure 3 - MPNST-G1/G2 distinct transcriptome
  (a) PCA whole transcriptome
  (b) DEG heatmap (logFC > 1, FDR < 0.05)
  (c) Top 10 pathways in MPNST-G1 (GSEA NES) and MPNST-G2 (GSEA NES)
  (d) SHH enrichment plot (G1 FDR 0.0075 NES 1.677; G2 FDR 0.397 NES -1.47), WNT enrichment (G1 FDR 0.319; G2 FDR 0.0201 NES 1.58)
  (e) Violin plots PTCH1, SMO, GLI2, GLI3, WNT10A, RAC2, RSPO2, APC (n = 49)
  (f) PTCH1 promoter methylation vs gene expression (r = -0.5129, p = 0.0002)

Figure 4 - snRNA-seq cellular architecture
  (a-c) t-SNE colored by sample/cell type/subgroup (43,365 nuclei)
  (d) Pairwise correlations
  (e) Bulk signatures correlation
  (f) Schwann/SCP/NCC markers

Figure 5 - SHH pathway therapeutic target
  (a-c) HSC1λ PTCH1 KO: GLI1 upregulation, proliferation, SHH pathway activation
  (d-f) ipNF06.2A PTCH1 KO: similar effects
  (g) HSC1λ anchorage-independent growth (132 vs 0 colonies)
  (h) HSC1λ migration (81 vs 0 cells)
  (i) ipNF06.2A migration (87.72 vs 41.07 cells)
  (j) GLI1/GLI2/SMO qPCR in 4 MPNST cell lines (S462, S462TY, T265 elevated; STS-26T not)
  (k) Sonidegib IC50 curves (S462TY two-fold lower than STS-26T)
  (l) Xenograft survival S462TY sonidegib vs vehicle (78 vs 45 days, p = 0.03); STS-26T no benefit

Figure 6 - Synopsis of PNST subgroups with gender, location, NF1, survival, methylation, CNV, mutation, targetable pathways

KEY SUPPLEMENTARY FIGURES:
Supp Fig 1 - Validation of MPNST-G1/G2 clustering in Toronto (silhouette 1.0, n=16), TCGA (0.98, n=5), DKFZ (0.67, n=33), Combined (0.60, n=54)
Supp Fig 2 - CpG methylation status by island/shore/shelf/open-sea, promoter/body/exon
Supp Fig 3 - WES oncoprints: (a) benign NF 41% NF1; (c) TCGA validation: 40% NF1, 20% SUZ12, 20% APC
Supp Fig 4 - Transcriptome clustering; adjusted Rand index 0.81 (Toronto), 0.76 (combined)
Supp Fig 5 - NF1 expression (ANOVA p < 0.01), RAS/RAF/MEK pathway no significant enrichment
Supp Fig 6 - WNT/BCAT/CYCLIN D1 GSEA enrichment plots
Supp Fig 7 - Promoter methylation vs gene expression correlations (PTCH1 r=-0.48, GAB1 r=-0.54, HIP1 r=-0.43, HES1 r=-0.35, ZEB1 r=-0.35, CTNNA2 r=0.57)
Supp Fig 8 - Fusion circos plots per subgroup; JARID2-ATP5MC2 in 33% of MPNST-G1
Supp Fig 9 - snRNA-seq clustering + inferCNV
Supp Fig 10-11 - snRNA-seq UMAP per subgroup/cluster/sample
Supp Fig 12 - Cell composition bar chart; LUMP scores Toronto (ANOVA p < 0.0001), DKFZ (p < 0.0001); Immune score (ANOVA p = 0.02)
Supp Fig 13 - Bulk signatures correlations, SMO/PTCH1/WNT11 expression
Supp Fig 14 - HSC1λ xenograft table: gGFP 0/4, gPTCH1 3/4, NF1-/- 6/12, NF1-/-;gPTCH1 4/4
Supp Fig 15 - CCND1 qPCR cell lines; methylation tSNE cell lines
Supp Fig 16 - Xenograft sonidegib table + GLI1/GLI2/GLI3 qPCR

SURVIVAL ANALYSES:
- Endpoint: Progression-free survival (PFS), defined as local tumor growth after gross total resection, tumor progression following subtotal resection, or distant metastasis
- Method: Kaplan-Meier with log-rank test
- Time variable: Elapsed time from index surgery to first postoperative imaging documenting recurrence (years)
- Key comparisons:
  - All methylation subgroups (Fig 1b, 75 samples): p < 0.0001 log-rank
  - MPNST-G1 vs MPNST-G2: median PFS 0.6 vs 1.4 years, p < 0.05
  - G3 (premalignant) vs benign NF (G4/G6/G7): p < 0.0001
  - Xenograft: S462TY-sonidegib vs S462TY-vehicle (78 vs 45 days, p = 0.03); STS-26T no benefit

SUPPLEMENTARY DATA FILES:
- Supp Data 1 (MOESM4): Patient demographics and data availability
- Supp Data 2 (MOESM5): All WES mutations (7457 rows)
- Supp Data 3 (MOESM6): Differentially expressed genes per subgroup
- Supp Data 4 (MOESM7): Computational drug screen for MPNST-G1 and MPNST-G2
- Supp Data 5 (MOESM8): All gene fusions identified (1031 fusions)
- Source data (MOESM10): Multi-sheet workbook with Fig 1b, 1f+g, 3c, 3f, 5a-l source data
"""

with open("/home/klkehl/Partners HealthCare Dropbox/Kenneth Kehl/chatbpc/multi_paper_analyses/papers/basic_science/PMC10172395/PMC10172395_claude_code_opus_4.7/paper_context.txt", "w") as f:
    f.write(context)


print(f"Total questions: {len(questions)}")
from collections import Counter
counts = Counter(q["category"] for q in questions)
for cat, n in counts.most_common():
    print(f"  {cat}: {n}")
print()
print("First 5 questions:")
for q in questions[:5]:
    print(f"\nID {q['analysis_id']} ({q['category']})")
    print(f"Q: {q['analysis_question']}")
    print(f"A: {q['reported_analysis_result']}")
