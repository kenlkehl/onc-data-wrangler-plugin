# example-synthetic-data Schema

## Table: `cohort`

- **Rows**: 50
- **Columns**: 7

| Column | Type | Nullable |
|--------|------|----------|
| `birth_year` | VARCHAR | YES |
| `naaccr_sex_code` | VARCHAR | YES |
| `race_ethnicity` | VARCHAR | YES |
| `age_at_diagnosis` | VARCHAR | YES |
| `os_status` | VARCHAR | YES |
| `os_months` | VARCHAR | YES |
| `number_of_cancers` | VARCHAR | YES |

## Table: `encounters`

- **Rows**: 1508
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 7

| Column | Type | Nullable |
|--------|------|----------|
| `date` | VARCHAR | YES |
| `diagnosis_code` | VARCHAR | YES |
| `department` | VARCHAR | YES |
| `visit_type` | VARCHAR | YES |
| `scenario_index` | BIGINT | YES |
| `scenario_label` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `extractions`

- **Rows**: 1101
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 82

| Column | Type | Nullable |
|--------|------|----------|
| `category` | VARCHAR | YES |
| `birth_year` | VARCHAR | YES |
| `naaccr_sex_code` | VARCHAR | YES |
| `race_ethnicity` | VARCHAR | YES |
| `age_at_diagnosis` | VARCHAR | YES |
| `os_status` | VARCHAR | YES |
| `os_months` | VARCHAR | YES |
| `number_of_cancers` | VARCHAR | YES |
| `tumor_index` | DOUBLE | YES |
| `primarySite` | VARCHAR | YES |
| `histologicTypeIcdO3` | VARCHAR | YES |
| `dateOfDiagnosis` | VARCHAR | YES |
| `laterality` | VARCHAR | YES |
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
| `img_dx_days` | VARCHAR | YES |
| `img_modality` | VARCHAR | YES |
| `img_body_region` | VARCHAR | YES |
| `img_overall_assessment` | VARCHAR | YES |
| `img_target_lesion_response` | VARCHAR | YES |
| `img_new_lesions` | VARCHAR | YES |
| `img_sites_of_disease` | VARCHAR | YES |
| `md_dx_days` | VARCHAR | YES |
| `md_ca` | VARCHAR | YES |
| `md_ca_status` | VARCHAR | YES |
| `md_ecog` | VARCHAR | YES |
| `rt_dx_days` | VARCHAR | YES |
| `rt_modality` | VARCHAR | YES |
| `rt_site` | VARCHAR | YES |
| `rt_dose_cgy` | VARCHAR | YES |
| `rt_fractions` | VARCHAR | YES |
| `rt_intent` | VARCHAR | YES |

## Table: `hospitalizations`

- **Rows**: 104
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 10

| Column | Type | Nullable |
|--------|------|----------|
| `admission_date` | VARCHAR | YES |
| `discharge_date` | VARCHAR | YES |
| `principal_dx_code` | VARCHAR | YES |
| `principal_dx_description` | VARCHAR | YES |
| `los_days` | BIGINT | YES |
| `discharge_disposition` | VARCHAR | YES |
| `reason` | VARCHAR | YES |
| `scenario_index` | BIGINT | YES |
| `scenario_label` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `labs`

- **Rows**: 5472
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 9

| Column | Type | Nullable |
|--------|------|----------|
| `date` | VARCHAR | YES |
| `test_name` | VARCHAR | YES |
| `value` | VARCHAR | YES |
| `unit` | VARCHAR | YES |
| `reference_range` | VARCHAR | YES |
| `abnormal_flag` | VARCHAR | YES |
| `scenario_index` | BIGINT | YES |
| `scenario_label` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `medications`

- **Rows**: 804
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 12

| Column | Type | Nullable |
|--------|------|----------|
| `drug_name` | VARCHAR | YES |
| `drug_category` | VARCHAR | YES |
| `start_date` | VARCHAR | YES |
| `end_date` | VARCHAR | YES |
| `route` | VARCHAR | YES |
| `dose` | VARCHAR | YES |
| `frequency` | VARCHAR | YES |
| `line_of_therapy` | BIGINT | YES |
| `intent` | VARCHAR | YES |
| `scenario_index` | BIGINT | YES |
| `scenario_label` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |

## Table: `pros`

- **Rows**: 3165
- **Unique patients**: 50 (multiple rows per patient; use COUNT(DISTINCT record_id) for patient-level denominators)
- **Columns**: 8

| Column | Type | Nullable |
|--------|------|----------|
| `date` | VARCHAR | YES |
| `instrument` | VARCHAR | YES |
| `subscale` | VARCHAR | YES |
| `value` | DOUBLE | YES |
| `scale_range` | VARCHAR | YES |
| `scenario_index` | BIGINT | YES |
| `scenario_label` | VARCHAR | YES |
| `data_source` | VARCHAR | YES |
