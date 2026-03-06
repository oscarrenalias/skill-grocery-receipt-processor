# Receipt Processing Skill Spec v1

## 1. Purpose

Build an agent skill that ingests Finnish grocery receipts, extracts line items, normalizes them into structured records, enriches them with English translations and taxonomy labels, and stores them in a local embedded database for historical analysis and natural-language search.

Primary target chains:

- Kesko / K-Citymarket / K-Supermarket / K-Market

The intended outcome is a SKILL.md file that will help agents understand how to operate the skill, as well as a command-line tool (written in Python) that will manage processing and persistence of the data. Inputs and outputs should be suitable for agentic processing, e.g., outputs should be structured JSON that an agent can process.

---

## 2. Objectives

The skill must:

1. Accept receipt input as PDF.
2. Extract text from the PDF before parsing.
3. Parse receipt-level metadata and item-level purchase records.
4. Enrich each item with:
   - original Finnish item name
   - English translation
   - grocery taxonomy category
   - quantity / weight
   - unit type
   - unit price
   - total line price
   - loyalty-discount flag and amount
5. Persist both raw and structured data locally.
6. Support later historical queries and semantic search.

---

## 3. Non-goals for v1

Exclude for now:

- perfect OCR for damaged/scanned receipts
- cross-store universal taxonomy
- VAT/tax accounting beyond capture of totals
- household budget dashboards
- automatic SKU matching against external product catalogs
- advanced deduplication across near-identical products

---

# 4. Input and Output

## 4.1 Supported input

### Input types

- PDF receipt
- optional raw extracted text

### Assumptions

- Receipts are digital PDFs, plain text, no images, that can be easily processed by extracting text out of the PDF file. No OCR required.
- receipt language is Finnish
- currency is EUR
- decimal separator may be comma

---

## 4.2 Output

### Structured receipt object

- store name
- store address
- transaction date/time
- transaction/reference id
- loyalty program totals
- payment total
- tax summary
- list of parsed line items
- list of discounts/refunds/returns
- parsing confidence
- warnings/errors

### Structured line-item object

- raw\_line\_text
- normalized\_finnish\_name
- english\_name
- category\_l1
- category\_l2
- category\_l3
- category\_path
- quantity
- unit\_type
- raw\_measure\_unit
- measure\_amount
- measure\_unit
- unit\_price\_eur
- line\_total\_eur
- loyalty\_discount\_amount\_eur
- loyalty\_discount\_type
- is\_weighted\_item
- is\_return\_or\_refund
- confidence
- parser\_notes

---

# 5. Processing Pipeline

## Stage A - Document ingestion

### A1 Load PDF

- read input PDF bytes
- compute document hash for idempotency
- store raw PDF path/hash metadata

### A2 Extract text

- Native text extraction first

### A3 Validate extracted text

Minimum checks:

- contains store header
- contains total line such as YHTEENSÄ
- contains multiple item rows
- contains date/time and payment block

---

## Stage B - LLM-first receipt segmentation and extraction

After text extraction, the raw receipt text should be provided to the LLM as the primary parser for segmentation and structuring.

### B1 Primary parsing approach

The LLM is responsible for:

- identifying receipt-level metadata
- segmenting the receipt into logical purchase records
- recognizing item lines, quantity/weight lines, discount lines, return/refund lines, totals, payment lines, and tax lines
- associating related lines into a single structured purchase record
- preserving original raw text for each extracted record

### B2 Deterministic preprocessing only

Local logic should be limited to lightweight preprocessing and normalization, such as:

- extracting plain text from the PDF
- preserving line order and line breaks
- normalizing whitespace

This preprocessing must not attempt to fully parse or classify receipt lines.

### B3 Fallback validation, not primary parsing

Deterministic logic may still be used after LLM extraction for validation and sanity checks, such as:

- verifying that a receipt total was extracted
- flagging missing item quantities or malformed numeric fields

The LLM should be treated as the primary receipt parser. Local heuristics should serve only as input cleanup, validation, and minor error detection.

---

# 6. LLM Extraction and Enrichment

## Responsibilities

For each grouped purchase record, the LLM should:

- normalize Finnish item name
- produce English translation
- infer category in grocery taxonomy
- interpret ambiguous unit formats
- determine whether discount applies to item
- generate confidence score

## LLM Should NOT

- extract text from PDF
- compute totals already present
- invent numeric values

---

## JSON extraction schema

```json
{
  "receipt": {
    "store_name": "string",
    "transaction_date": "YYYY-MM-DD",
    "transaction_time": "HH:MM",
    "currency": "EUR"
  },
  "items": [
    {
      "raw_name_fi": "string",
      "normalized_name_fi": "string",
      "english_name": "string",
      "category": "string",
      "quantity": 0,
      "unit_type": "piece|weight|volume|pack|unknown",
      "raw_measure_unit": "kpl|kg|g|l|ml|pkt|unknown",
      "measure_unit": "piece|kg|g|l|ml|pack|unknown",
      "measure_amount": 0,
      "unit_price_eur": 0,
      "line_total_eur": 0,
      "loyalty_discount_amount_eur": 0,
      "loyalty_discount_type": "PLUSSA|OMA_PLUSSA|KAMPANJA|TASAERA|NONE",
      "is_weighted_item": false,
      "is_return_or_refund": false,
      "confidence": 0.0,
      "notes": "string"
    }
  ]
}
```

---

# 7. Parsing Rules

## Numeric normalization

Normalize:

- 7,26 -> 7.26
- 0,485 KG -> 0.485 KG
- 0,52- -> -0.52

---

## Unit handling

The LLM should extract the raw Finnish unit exactly as it appears on the receipt and map it to a canonical English unit.

Canonical unit mapping must not be left to free-form translation. The system should maintain a deterministic mapping table and require the LLM to use only supported canonical values.

Examples:

- KPL -> piece
- KG -> kg
- G -> g
- L -> l
- ML -> ml
- PKT -> pack

Recommended fields:

- `raw_measure_unit`: raw unit from the receipt, e.g. `KPL`
- `measure_unit`: canonical English unit, e.g. `piece`
- `unit_type`: higher-level semantic grouping, e.g. `piece`, `weight`, `volume`, `pack`

If the LLM encounters an unsupported or ambiguous unit, it should preserve the raw unit, set the canonical unit to `unknown`, and lower confidence accordingly.

---

## Weighted items

Pattern:

- item line contains total price
- next line contains weight and price per KG

Store as:

- quantity = weight
- measure\_amount = weight
- unit\_type = weight
- raw\_measure\_unit = KG
- measure\_unit = kg
- unit\_price\_eur = parsed kg price
- line\_total\_eur = item price

---

## Multi-quantity packaged items

Pattern:

- item line contains total price
- next line contains quantity and price per piece

Store as:

- quantity = item count
- measure\_amount = item count
- unit\_type = piece
- raw\_measure\_unit = KPL
- measure\_unit = piece
- unit\_price\_eur = parsed unit price
- line\_total\_eur = item price

---

## Loyalty and campaign discounts

Recognize markers such as:

- PLUSSA-ETU
- OMA PLUSSA-ETU
- KAMPANJA-ETU
- TASAERÄ
- PLUSSA-TASAERÄ

Attribution rule for v1:

Attach discount line to nearest preceding eligible item within small window. If ambiguous, store at receipt level.

---

## Refunds and deposits

Lines such as bottle-return refunds should be treated as financial adjustments, not grocery items.

---

# 8. Taxonomy Model

Use a controlled taxonomy.

### Suggested 3-level taxonomy

The taxonomy should support hierarchical classification rather than a single flat category.

Recommended structure:

- `category_l1`: broad domain
- `category_l2`: family or department
- `category_l3`: specific product grouping

Suggested v1 hierarchy:

- `food`

  - `produce`
    - `fruit`
    - `vegetables`
    - `herbs`
    - `mushrooms`
  - `meat_and_seafood`
    - `meat`
    - `poultry`
    - `fish_and_seafood`
    - `processed_meat`
  - `dairy_and_eggs`
    - `milk_and_cream`
    - `yogurt_and_quark`
    - `cheese`
    - `butter_and_spreads`
    - `eggs`
  - `bakery`
    - `bread`
    - `pastries`
    - `cakes_and_desserts`
  - `pantry`
    - `pasta_rice_grains`
    - `flour_and_baking`
    - `canned_and_jarred`
    - `sauces_and_condiments`
    - `oils_and_fats`
    - `spices_and_seasonings`
  - `frozen`
    - `frozen_meals`
    - `frozen_vegetables`
    - `frozen_desserts`
  - `snacks_and_sweets`
    - `chips_and_salty_snacks`
    - `candy`
    - `chocolate`
    - `biscuits_and_cookies`
  - `beverages`
    - `water`
    - `soft_drinks`
    - `juice`
    - `coffee`
    - `tea`
    - `alcoholic_beverages`
    - `other_beverages`
  - `prepared_food`
    - `ready_meals`
    - `deli`
    - `takeaway`

- `non_food`

  - `household`
    - `cleaning_supplies`
    - `paper_products`
    - `storage_and_wrapping`
  - `personal_care`
    - `soap_and_shower`
    - `oral_care`
    - `hair_care`
    - `skin_care`
  - `baby`
    - `diapers`
    - `baby_food`
    - `baby_care`
  - `pet`
    - `pet_food`
    - `pet_care`

- `other`

  - `financial_adjustments`
    - `refunds_and_deposits`
    - `loyalty_discounts`
    - `campaign_discounts`
  - `services`
    - `delivery_or_fees`
    - `other_services`
  - `unknown`
    - `uncategorized`

Recommended output fields:

- `category_l1`
- `category_l2`
- `category_l3`

A flattened derived field such as `category_path` may also be stored, for example:

- `food > dairy_and_eggs > cheese`

Taxonomy should be versioned independently of the parser so categories can evolve without reprocessing the raw receipt text.

---

# 9. Storage Design

## Recommended architecture

Use SQLite as the system of record.

The persistence model should include a `receipts` table for receipt-level metadata and raw extracted text, a `receipt_items` table for parsed line items, and a `receipt_adjustments` table for refunds, deposits, and other non-item financial adjustments.

Vector embeddings may be added later to support RAG and semantic searches.

---

## Tables

### receipts

- receipt\_id
- document\_hash
- source\_file
- store\_name
- store\_address
- transaction\_date
- transaction\_time
- currency
- reported\_total\_eur
- raw\_text
- extraction\_method
- created\_at

---

### receipt\_items

- item\_id
- receipt\_id
- line\_index
- raw\_name\_fi
- normalized\_name\_fi
- english\_name
- category\_l1
- category\_l2
- category\_l3
- category\_path
- quantity
- unit\_type
- raw\_measure\_unit
- measure\_unit
- measure\_amount
- unit\_price\_eur
- line\_total\_eur
- loyalty\_discount\_amount\_eur
- loyalty\_discount\_type
- is\_weighted\_item
- is\_return\_or\_refund
- confidence
- parser\_notes

---

### receipt\_adjustments

- adjustment\_id
- receipt\_id
- type
- raw\_text
- amount\_eur
- applies\_to\_item\_id

---

# 10. Search Strategy

Will be defined at a later stage..

---

# 11. Agent Skill Interface

## Command Input

The tool should be operated as a command-line interface rather than requiring JSON input. This makes it easier for humans to run the tool while still allowing agents to call it programmatically.

Example usage:

```bash
receipt-processor --input /path/to/receipt.pdf
```

Common parameters:

- `--input <path>` Path to the receipt PDF to process.

- `--persist` Persist the parsed receipt and items to the local SQLite database.

- `--debug` Enable verbose logging and include additional diagnostic information in the output.

- `--output <path>` Optional path where the structured JSON result should be written.

Example:

```bash
receipt-processor \
  --input ./receipts/citymarket-2026-03-01.pdf \
  --persist \
  --debug
```

The command should always emit structured JSON to stdout so that agents can consume the result programmatically.

---

## Command Output

```json
{
  "status": "ok",
  "receipt_id": "uuid",
  "store_name": "K-Citymarket",
  "transaction_date": "YYYY-MM-DD",
  "total_eur": 0,
  "items_extracted": 0,
  "adjustments_extracted": 0,
  "warnings": []
}
```

---

# 12. Validation

## Receipt-level validation

Check:

- sum of item totals roughly matches receipt total
- transaction date exists
- at least one item exists

---

## Item-level validation

Check:

- quantity > 0
- line total >= 0 unless refund

---

# 13. Error Handling

Possible statuses:

- TEXT\_EXTRACTION\_FAILED
- PARSE\_PARTIAL
- TOTAL\_MISMATCH
- PERSIST\_FAILED

The CLI and agent interface should always return structured JSON even when errors occur.

### Example: text extraction failure

```json
{
  "status": "error",
  "error_code": "TEXT_EXTRACTION_FAILED",
  "message": "Failed to extract text from PDF",
  "receipt": null,
  "items": [],
  "adjustments": [],
  "warnings": []
}
```

### Example: partial parse

```json
{
  "status": "partial",
  "error_code": "PARSE_PARTIAL",
  "message": "Some receipt lines could not be parsed",
  "receipt": {
    "store_name": "K-Citymarket",
    "transaction_date": "2026-03-01",
    "currency": "EUR"
  },
  "items": [
    {
      "raw_line_text": "Pirkka täysmaito 1 l 2,90",
      "raw_name_fi": "Pirkka täysmaito",
      "english_name": "whole milk",
      "quantity": 2,
      "unit_type": "piece",
      "measure_unit": "piece",
      "line_total_eur": 2.90,
      "confidence": 0.92
    }
  ],
  "unparsed_lines": [
    "EPÄSELVÄ RIVI 123"
  ],
  "warnings": [
    "1 receipt line could not be interpreted"
  ]
}
```

### Example: validation error

```json
{
  "status": "error",
  "error_code": "TOTAL_MISMATCH",
  "message": "Sum of parsed items does not match receipt total",
  "receipt": {
    "store_name": "K-Citymarket",
    "transaction_date": "2026-03-01",
    "reported_total_eur": 42.83
  },
  "items": [],
  "warnings": [
    "Parsed totals differ from receipt total"
  ]
}
```

Raw text should always be persisted even on partial failures.

---

# 14. Privacy

- redact payment card fragments
- redact PII data, if any
