# Glossary

| Term | Meaning here |
|---|---|
| **pile** | the unsorted mass of files a business receives: email attachments, phone photos, scans, spreadsheets, e-invoices. Also the package name. |
| **file / document** | a file is what arrives; a document is one business document. One file can hold several (a supplier pack); one document can span several files (page 2 sent separately). |
| **PO** | purchase order, raised by the buyer (the CRM's customer) to a supplier |
| **GRN** | goods received note: the buyer's record of what arrived. The client's word for receipt. |
| **docket / delivery docket** | the supplier's delivery paper, often signed on site and photographed. Treated as a goods receipt. |
| **supplier invoice / tax invoice** | the bill. In Australia a tax invoice must meet ATO requirements (ABN, "tax invoice", GST, buyer identity at $1,000 or more). |
| **credit note / adjustment note** | reduces an invoice |
| **statement** | the supplier's monthly list of what it thinks the buyer owes; corroborates invoices and payments, and reveals invoices never received |
| **remittance advice** | the buyer's notice of payment: which invoices, how much |
| **price schedule** | agreed prices for a period |
| **pendency** | the client's word for an outstanding balance. Three kinds: goods owed, paperwork owed, money owed. |
| **goods owed** | ordered, not yet received (PO to GRN) |
| **paperwork owed** | received, not yet invoiced (GRN to invoice); SAP's "GR surplus" |
| **money owed** | invoiced, not yet paid (invoice to payment) |
| **invoiced not received** | billed beyond what arrived; SAP's "IR surplus"; the brief's "missing receipt" |
| **chain** | PO, receipts, invoices, credits and payments that belong together |
| **grounding** | finding a value on the page as an exact token, by a reading independent of the one that produced it |
| **gate** | the decision per document: read (accepted as fact), flagged (through, confirm), held (a person must act) |
| **blocked_on** | why a field is not settled: `extraction_quality` (read badly) or `corroboration` (waiting on other documents) |
| **evidence** | why a value is believed: label, master (supplier list), layout (letterhead), model, structure |
| **text layer** | the text inside a born-digital PDF; exact and free to read |
| **UBL / Peppol PINT A-NZ** | the XML e-invoice standard used in Australia and New Zealand; the only format on the Peppol network since 15 May 2025 |
| **ABN** | Australian Business Number; 11 digits with a checksum (`normalise.abn_valid`) |
| **trust boundary** | the line between the model (reads) and the code (decides) |
| **Ridgeline** | the invented fabricator in the synthetic corpus; all its suppliers, ABNs and numbers are invented |
