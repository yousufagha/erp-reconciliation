# Client context

Everything known about the client and what they asked for, with how strongly each point is
established. Where the client's words exist they are quoted, not paraphrased.

## Who

- **Client:** a software vendor that sells a CRM. (Confirmed by Yousuf, 10 Sep 2026.)
- **Their customers:** fabrication and building-materials companies. (Confirmed, 10 Sep.)
- **The task:** integrate reconciliation into the existing CRM so that "multiple invoices and
  other documents are balanced, resolved and accounted for". Invoices and other documents
  are "already handled but they lack intelligence and reconciliation that is automatic and
  smart". (Yousuf relaying the client, 10 Sep.)
- **Shape:** a module inside their codebase: their stack, their schema, their release train.
  The stack is **not yet known**. That is why this repo is a library, not an app.

## What the CRM already has

| Capability | Status | Strength of evidence |
|---|---|---|
| Customers and sales pipeline | has it | confirmed |
| Job / project records | has it | confirmed |
| Document storage | has it | confirmed |
| Quote/estimate builder | does not have it | **weak**: answered by omission on a multiple-choice question |
| Supplier purchase orders | does not hold them | **weak**: as above. Says nothing about whether their customers raise POs elsewhere |
| Accounting package | varies by customer | confirmed; whether the CRM syncs to any is unknown |

## The brief

`client/brief.md` is the client's scope document. Its core: a three-way match (PO, goods
receipt, vendor bill) with LLM-based extraction ("not brittle OCR templates"), tolerance-based
auto-approval, exceptions explained in plain language and bucketed into five types, one-click
resolution with rule learning, landed cost allocation, GL posting with a full audit trail, and
the metric "% of bills requiring human touch". It was written for DTC brands and importers
and includes Shopify/Amazon sync, since struck (below).

## The client's correction, 14 Sep 2026 (WhatsApp, verbatim)

> **12:45** "One correction : purchase order always created"
>
> **12:46** "Purchase order …. GRN ( material reviving) …. Supplier Invoice …. Payment to supplier"
>
> **12:49** "The vendor reconciliation start from the purchase order raised by customer ….
> Against purchase order how many line items are send and what qty … what is pendency ….
> Against each GRN how many invoice is raised and how much is pendency and against how many
> purchase invoice how much amount is paid and how much pendency"

Followed by screenshots of their own AI research: a five-step vendor reconciliation workflow,
a tools comparison (n8n, ERP-native automation, Make, SAP Integration Suite) and an automated
supplier statement reconciliation example.

What it establishes:

1. **Purchase orders are always created.** The PO is the spine.
2. **The chain has four stages:** PO, GRN, supplier invoice, payment to supplier.
3. **They say GRN.** Use their word.
4. **The deliverable is pendency** (outstanding balance) at three junctions, not an exception
   queue. Matching is the mechanism; pendency is the product.
5. They benchmark against ERP-native and SAP approaches.

## Answers to the five blocking questions, 14 Sep 2026 (verbatim)

**Channel sync:** "no, we dont care much for shopify and amazon styles unless they have someting
unique that solves our problem". Flow 4 and Phase 3 channel work are struck.

**Who raises the PO:** "the po is done by the company we provide our CRM to". This answers
*who*, not *in which system*. The design holds the PO as a record filled by entry or import,
so it does not matter yet.

**Where payment data comes from:** "the payment data comes from other documents like invoices,
receipts". Not a bank feed, not an accounting integration: payment is a document-reading
problem (remittance advices, statements).

**Scope and the mission statement:**

> "if it is mentinoed in his file, then it is good to assume they do, point is the program
> should be able to work through all kinds of files and file types, process their numbers and
> create resolution among the chaos of all these files and tell us accurately the status of
> the paperwork and the real goods"

This is the clearest statement of the brief anyone has given. Two consequences drive the
architecture: the input is a **pile, not a pipeline** (any order, any format, duplicates,
partial chains), and "the status of the paperwork **and** the real goods" is two answers.

## The three pendencies

| Junction | Name used here | Meaning |
|---|---|---|
| PO to GRN | goods owed | ordered, not yet delivered |
| GRN to invoice | paperwork owed | received, not yet invoiced |
| invoice to payment | money owed | invoiced, not yet paid |

SAP's GR/IR reconciliation uses the same idea: "GR Amount Surplus" is paperwork owed;
"IR Amount Surplus" is invoiced but not received (the brief's "missing receipt").

## Documents in scope

Supplier invoices, credit notes, delivery dockets and GRNs, monthly supplier statements, price
schedules, purchase orders, remittance advices. Out of scope: subcontractor progress claims
and retention.

## Standing rule

Nothing about the client's customers' working practices is established beyond the above.
Until real documents and a customer conversation arrive, phrase it as a question. See
`05-decisions.md` D-00 for why this rule exists.
