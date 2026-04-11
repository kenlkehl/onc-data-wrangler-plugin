# example-synthetic-data Schema

## Table: `cohort`

- **Rows**: 50
- **Columns**: 0

| Column | Type | Nullable |
|--------|------|----------|

## Table: `diagnoses`

- **Rows**: 108
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 35

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `primarySite` | VARCHAR | YES |
| `histologicTypeIcdO3` | VARCHAR | YES |
| `dateOfDiagnosis` | VARCHAR | YES |
| `laterality` | VARCHAR | YES |
| `birth_year` | VARCHAR | YES |
| `naaccr_sex_code` | VARCHAR | YES |
| `race_ethnicity` | VARCHAR | YES |
| `age_at_diagnosis` | VARCHAR | YES |
| `os_status` | VARCHAR | YES |
| `os_months` | VARCHAR | YES |
| `number_of_cancers` | VARCHAR | YES |
| `ca_seq` | VARCHAR | YES |
| `cohort` | VARCHAR | YES |
| `ca_type` | VARCHAR | YES |
| `naaccr_histology_code` | VARCHAR | YES |
| `ca_hist_adeno_squamous` | VARCHAR | YES |
| `naaccr_primary_site` | VARCHAR | YES |
| `ca_stage` | VARCHAR | YES |
| `ca_tnm_t` | VARCHAR | YES |
| `ca_tnm_n` | VARCHAR | YES |
| `ca_tnm_m` | VARCHAR | YES |
| `ca_dmets_yn` | VARCHAR | YES |
| `dmets_brain` | VARCHAR | YES |
| `dmets_bone` | VARCHAR | YES |
| `dmets_liver` | VARCHAR | YES |
| `dmets_lung` | VARCHAR | YES |
| `dmets_lymph` | VARCHAR | YES |
| `dmets_adrenal` | VARCHAR | YES |
| `dmets_pleura` | VARCHAR | YES |
| `dmets_peritoneum` | VARCHAR | YES |
| `dmets_other` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `encounters`

- **Rows**: 1508
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 7

| Column | Type | Nullable |
|--------|------|----------|
| `source` | VARCHAR | YES |
| `encounter_date` | VARCHAR | YES |
| `diagnosis_code` | VARCHAR | YES |
| `department` | VARCHAR | YES |
| `visit_type` | VARCHAR | YES |
| `cancer_type` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `genomics`

- **Rows**: 109
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 15

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `ngs_dx_days` | VARCHAR | YES |
| `ngs_panel` | VARCHAR | YES |
| `ngs_specimen_type` | VARCHAR | YES |
| `ngs_tmb` | VARCHAR | YES |
| `ngs_msi_status` | VARCHAR | YES |
| `ngs_mutations` | VARCHAR | YES |
| `ngs_fusions` | VARCHAR | YES |
| `ngs_amplifications` | VARCHAR | YES |
| `ngs_pdl1_tps` | VARCHAR | YES |
| `ngs_pdl1_cps` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `hospitalizations`

- **Rows**: 104
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 9

| Column | Type | Nullable |
|--------|------|----------|
| `source` | VARCHAR | YES |
| `admission_date` | VARCHAR | YES |
| `discharge_date` | VARCHAR | YES |
| `principal_diagnosis_code` | VARCHAR | YES |
| `principal_diagnosis_description` | VARCHAR | YES |
| `los_days` | BIGINT | YES |
| `discharge_disposition` | VARCHAR | YES |
| `reason` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `imaging`

- **Rows**: 242
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 12

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `img_dx_days` | VARCHAR | YES |
| `img_modality` | VARCHAR | YES |
| `img_body_region` | VARCHAR | YES |
| `img_overall_assessment` | VARCHAR | YES |
| `img_target_lesion_response` | VARCHAR | YES |
| `img_new_lesions` | VARCHAR | YES |
| `img_sites_of_disease` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `labs`

- **Rows**: 5472
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 8

| Column | Type | Nullable |
|--------|------|----------|
| `source` | VARCHAR | YES |
| `test_date` | VARCHAR | YES |
| `test_name` | VARCHAR | YES |
| `value` | DOUBLE | YES |
| `unit` | VARCHAR | YES |
| `reference_range` | VARCHAR | YES |
| `abnormal_flag` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `medications`

- **Rows**: 804
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 11

| Column | Type | Nullable |
|--------|------|----------|
| `source` | VARCHAR | YES |
| `drug_name` | VARCHAR | YES |
| `drug_category` | VARCHAR | YES |
| `start_date` | VARCHAR | YES |
| `end_date` | VARCHAR | YES |
| `route` | VARCHAR | YES |
| `dose` | VARCHAR | YES |
| `frequency` | VARCHAR | YES |
| `line_of_therapy` | VARCHAR | YES |
| `intent` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `medonc`

- **Rows**: 115
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 9

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `md_dx_days` | VARCHAR | YES |
| `md_ca` | VARCHAR | YES |
| `md_ca_status` | VARCHAR | YES |
| `md_ecog` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `pathology`

- **Rows**: 157
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 15

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `path_report_type` | VARCHAR | YES |
| `path_dx_days` | VARCHAR | YES |
| `path_histology` | VARCHAR | YES |
| `path_grade` | VARCHAR | YES |
| `path_margins` | VARCHAR | YES |
| `path_lvi` | VARCHAR | YES |
| `path_pni` | VARCHAR | YES |
| `path_tumor_size_cm` | VARCHAR | YES |
| `path_nodes_positive` | VARCHAR | YES |
| `path_nodes_examined` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `pros`

- **Rows**: 3165
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 7

| Column | Type | Nullable |
|--------|------|----------|
| `source` | VARCHAR | YES |
| `assessment_date` | VARCHAR | YES |
| `instrument_name` | VARCHAR | YES |
| `subscale` | VARCHAR | YES |
| `value` | DOUBLE | YES |
| `scale_range` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `radiation`

- **Rows**: 47
- **Unique patients**: 24 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 11

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `rt_dx_days` | VARCHAR | YES |
| `rt_modality` | VARCHAR | YES |
| `rt_site` | VARCHAR | YES |
| `rt_dose_cgy` | VARCHAR | YES |
| `rt_fractions` | VARCHAR | YES |
| `rt_intent` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `regimens`

- **Rows**: 239
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 16

| Column | Type | Nullable |
|--------|------|----------|
| `tumor_index` | BIGINT | YES |
| `category` | VARCHAR | YES |
| `instance_index` | DOUBLE | YES |
| `regimen_number` | VARCHAR | YES |
| `regimen_drugs` | VARCHAR | YES |
| `drugs_num` | VARCHAR | YES |
| `regimen_setting` | VARCHAR | YES |
| `dx_reg_start_days` | VARCHAR | YES |
| `dx_reg_end_days` | VARCHAR | YES |
| `regimen_ongoing` | VARCHAR | YES |
| `regimen_disc_reason` | VARCHAR | YES |
| `includes_immunotherapy` | VARCHAR | YES |
| `includes_targeted` | VARCHAR | YES |
| `includes_chemo` | VARCHAR | YES |
| `source` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |
