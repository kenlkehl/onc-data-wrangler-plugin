---
name: build-ontology
description: Create a custom ontology definition from a data dictionary or codebook. Generates YAML ontology files that can be used for extraction. Use when the user has a data dictionary and wants to define extraction fields.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: high
---

# Build Custom Ontology

You are helping the user create a custom ontology definition from their data dictionary or codebook. The ontology defines the structured fields that can be extracted from clinical notes.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 1: Read Data Dictionary

Accept the path to a data dictionary file (Excel, CSV, or PDF).

For Excel/CSV files, read and profile the contents:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
import pandas as pd
df = pd.read_excel('DICT_PATH')  # or read_csv
print(f'Columns: {list(df.columns)}')
print(df.head(10).to_string())
print(f'Total items: {len(df)}')
"
```

For PDF files, read directly and extract field definitions.

Identify which columns contain:
- Field/variable ID
- Field/variable name
- Description
- Data type
- Valid values / code table
- Category/group

## STEP 2: Design Ontology Structure

Ask the user:
1. **Ontology ID** (kebab-case, e.g., `my-registry`)
2. **Display name** (e.g., "My Cancer Registry")
3. **Description**
4. How to group items into categories (by section in the dictionary, or let Claude suggest based on clinical domain)

## STEP 3: Generate YAML

Create the ontology YAML file at `${CLAUDE_PLUGIN_ROOT}/data/ontologies/<ontology_id>/ontology.yaml`:

```yaml
id: my-registry
name: My Cancer Registry
description: Custom ontology for ...
is_free_text: false
categories:
  - id: demographics
    name: Demographics
    description: Patient demographic information
    items:
      - id: "field_001"
        name: patient_age
        description: "Age at diagnosis in years"
        data_type: integer
        length: 3
      - id: "field_002"
        name: sex
        description: "Patient sex"
        data_type: code
        length: 1
        valid_values:
          - code: "1"
            description: "Male"
          - code: "2"
            description: "Female"
          - code: "9"
            description: "Unknown"
  # ... more categories and items
```

## STEP 4: Generate Code Tables (Optional)

If the data dictionary has extensive code tables, create CSV files in `${CLAUDE_PLUGIN_ROOT}/data/ontologies/<ontology_id>/codes/`:

```csv
field_id,code,description
field_002,1,Male
field_002,2,Female
field_002,9,Unknown
```

## STEP 5: Verify

Verify the ontology loads correctly:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.ontologies.registry import OntologyRegistry
ont = OntologyRegistry.get('ONTOLOGY_ID')
items = ont.get_base_items()
total = sum(len(cat.items) for cat in items)
print(f'Loaded ontology: {ont.name}')
print(f'Categories: {len(items)}')
print(f'Total items: {total}')
for cat in items:
    print(f'  {cat.name}: {len(cat.items)} items')
"
```

Report success and suggest using the ontology with `/onc-data-wrangler:extract-notes` or `/onc-data-wrangler:make-database`.
