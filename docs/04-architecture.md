# Architecture

## 1. Placement

The module sits inside the client's CRM. It reads the documents the CRM already stores, uses
what the CRM already knows (its own company, its supplier list, later its jobs), and hands back
chains, pendency and exceptions. Posting to an accounting package goes out through one adapter
(not built).

```mermaid
flowchart LR
  subgraph CRM["Client's CRM (stack unknown)"]
    DS[(Document storage)]
    SUP[(Supplier list)]
    CO[(Own company)]
    UI[Screens]
  end
  subgraph PILE["pile (this repo)"]
    P[Read the pile] --> R[Resolve chains]
    R --> O[Pendency + exceptions]
  end
  DS -- files --> P
  SUP -- context --> P
  CO -- context --> P
  O --> UI
  O -. adapter, not built .-> ACC[(Xero / MYOB / QBO)]
```

## 2. The pipeline

Ten stages from "Reading the Pile" (design, 14 Sep). The cheap, certain stages run first;
reading is the expensive step, so nothing is read twice.

```mermaid
flowchart TD
  A[1 Intake<br/>files, email unpacked] --> B[2 Dedupe<br/>byte hash before reading]
  B --> C[3 Profile<br/>format, text layer or image, pages]
  C --> D{4 Read}
  D -->|UBL e-invoice| D1[Structure<br/>no model]
  D -->|xlsx csv docx email text| D2[Grid<br/>no model]
  D -->|PDF text layer| D3[Words with positions<br/>no model]
  D -->|photo, scan| D4[Model reads page<br/>+ Tesseract reads same page]
  D1 & D2 & D3 & D4 --> E[5 Classify<br/>printed title]
  E --> F[6 Extract<br/>per-type schema]
  F --> S[Split and join<br/>file is not a document]
  S --> G[7 Validate<br/>arithmetic, ATO rules]
  G --> H[8 Ground<br/>value on the page?]
  H --> I[10 Gate<br/>read, flagged or held]
  I --> J[9 Resolve<br/>chains, pendency, exceptions]
  J --> K[Status report]
```

Stage numbers follow the design; in code, grounding and the gate run inside `pipeline.gate`
and `image_read`, and resolution runs over everything that passed.

## 3. The trust boundary

The model occupies exactly one box, and it is not a box that changes a number.

```mermaid
flowchart LR
  subgraph MODEL["Model (may be wrong)"]
    M1[Read a page image<br/>into the schema,<br/>values as printed]
  end
  subgraph CODE["Deterministic code (decides)"]
    C1[Parse values] --> C2[Ground against OCR]
    C2 --> C3[Arithmetic checks]
    C3 --> C4[Confidence]
    C4 --> C5[Gate]
    C5 --> C6[Link, match,<br/>pendency]
  end
  subgraph PERSON["Person"]
    P1[Confirm flagged,<br/>resolve held]
  end
  M1 --> C1
  C5 -->|flagged / held| P1
  P1 --> C6
```

`tests/test_trust_boundary.py` fails the build if any deciding module can import a model
client or the model reader. Only `model_read.py` may import one.

## 4. Reading without guessing

Every accepted value has evidence. Evidence is recorded per field (`FieldValue.evidence`,
`FieldValue.printed`, `FieldValue.grounded`).

| Source of a value | Evidence required | If missing |
|---|---|---|
| UBL e-invoice | the element that holds it | not applicable |
| Spreadsheet, Word, email, PDF text | a printed label, or a column heading over it | left blank |
| Supplier name | supplier list match, or a label; letterhead only with a flag | blank, or flagged |
| Numeric date like 03/04/2026 | an unambiguous date or an ABN on the same document | flagged |
| Model reading of an image | found on the page by Tesseract as a whole token | capped at 0.35 confidence, held |
| Line numbers from a model | every quantity, price, amount, code on the page | document held |
| Totals | lines sum to subtotal, subtotal plus GST to total, GST 10% | document held |

A number inside a longer code does not ground: quantity 12 is not found in `TMB-140x45-MGP12`.

## 5. The gate

```mermaid
flowchart TD
  A[Document read] --> Q1{Did the read<br/>yield anything?}
  Q1 -->|no| H[Held]
  Q1 -->|yes| Q2{Does its own<br/>arithmetic hold?}
  Q2 -->|no| H
  Q2 -->|yes| Q3{Model read:<br/>weakest material field}
  Q3 -->|below 0.75 and not on page| H
  Q3 -->|0.75 to 0.92| FL[Flagged:<br/>through, confirm]
  Q3 -->|0.92 and above,<br/>or not a model read| Q4{Any value<br/>inferred?}
  Q4 -->|letterhead name,<br/>ambiguous date| FL
  Q4 -->|no| R[Read: accepted as fact]
```

`blocked_on` says why: `extraction_quality` (we read it badly; a better reader or a person
fixes it) or `corroboration` (fine as read, waiting on other documents). Thresholds are
uncalibrated.

## 6. Split and join

A wrong split is silent (two half-invoices, each plausible). A wrong join is loud (the
arithmetic fails). So pages are cut only on strong evidence.

```mermaid
flowchart LR
  subgraph cut["Cut between pages when"]
    a1[page numbering restarts]
    a2[new title with a<br/>different document number]
    a3[document type changes]
  end
  subgraph keep["Keep together when"]
    b1[page says continued]
    b2[page 1 of 2]
    b3[no strong evidence]
  end
```

Joining across files: a page that says it continues, arriving as its own file, attaches to the
document whose number it names.

## 7. Resolution

```mermaid
flowchart LR
  PO[Purchase order<br/>lines: sku, qty, price] -->|received| GRN[GRN / docket]
  PO -->|invoiced| INV[Supplier invoice]
  CN[Credit note] -->|reduces| INV
  RA[Remittance] -->|pays| INV
  ST[Supplier statement] -. corroborates .-> INV
  ST -. lists what we never got .-> MISS[Missing document]
```

Links, in order of trust:

1. **The PO number printed on the document**, accepted only if the supplier matches the PO's
   (a PO number quoted by another supplier is not trusted).
2. **An auditable score** when no usable number: supplier 0.35, amount 0.25, date 0.15, line
   overlap 0.25. At or above 0.85 links; 0.60 to 0.85 links with low confidence; below, no
   matching PO.

Line matching: same SKU; else the PO's SKU printed inside the description; else description
word overlap of 0.6 or more.

Registers, per PO line:

- goods owed = ordered minus received
- paperwork owed = received minus (invoiced minus credited)
- invoiced not received = (invoiced minus credited) minus received
- money owed, per invoice = total minus credits minus remitted

Exceptions: price variance (beyond 2%, the brief's example tolerance), quantity variance
(resolved when a credit brings net invoiced down to received), no matching PO, duplicate
suspected (same type, supplier and number from different files), missing receipt, missing
document (on a statement, never received). Unread documents make the report provisional, and
when OCR can see which PO an unread docket names, the exception says so.

## 8. Data model

```mermaid
classDiagram
  class Item {
    ref: file or file#attachment
    sha256
    origin: sender, subject, date
  }
  class ReadDocument {
    sources: SourceRef[]
    doc_type: DocType
    fields: name to FieldValue
    lines: dict[]
    status: read | flagged | held | duplicate
    checks: Check[]
    model_read: bool
  }
  class FieldValue {
    value
    printed
    evidence: label | master | layout | model
    grounded: bool | None
    confidence
    blocked_on
  }
  class SourceRef {
    file
    pages
  }
  class Resolution {
    goods_owed
    paperwork_owed
    invoiced_not_received
    money_owed
    exceptions
    unread
    corroboration
  }
  Item --> ReadDocument : read into 0..n
  ReadDocument --> SourceRef : 1..n
  ReadDocument --> FieldValue
  ReadDocument --> Resolution : resolved into
```

Eight document types, each with its own header fields (`models.HEADER_FIELDS`) and its own
check (`validate.py`):

| Type | Own check |
|---|---|
| supplier_invoice | lines multiply out, sum to subtotal; subtotal + GST = total; GST 10%; ATO fields |
| credit_note | same arithmetic; names the invoice it credits |
| goods_receipt | quantities present; quotes a PO |
| statement | opening + entries = closing balance |
| price_schedule | effective dates in order; prices present |
| purchase_order | same arithmetic as an invoice |
| remittance | allocations sum to amount remitted |
| unknown | none; held |

## 9. Model path detail

```mermaid
sequenceDiagram
  participant P as pipeline
  participant I as image_read
  participant M as model_read (Gemini)
  participant O as ocr (Tesseract)
  participant G as gate
  P->>I: page images
  I->>O: read each page
  O-->>I: words with positions, confidence
  I->>M: each page, schema, "values as printed"
  M-->>I: doc_type, fields, lines (strings)
  I->>I: group pages (same boundary rules)
  I->>I: parse, ground every value, compare with OCR label pass
  I->>G: document with per-field confidence
  G-->>P: read, flagged or held
```

With no model configured, OCR only labels the document provisionally (type, number, PO) so the
report can say what is waiting; the document is held. OCR is not trusted to read line items:
on a tilted photo it attaches quantities to the wrong rows, and a docket has no arithmetic to
catch that.

## 10. What is not built

Tolerance scoping and rule learning, blast-radius preview, landed cost, GL posting adapter,
screens, background worker, authentication, tenancy, job coding, price schedule variance
checks. The 9 Sep build had several of these; they were lost with its workspace. See
`07-open-questions.md`.
