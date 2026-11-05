# dealroom-copilot

A due-diligence assistant for a private-equity data room. You ask a question, it answers from the documents and shows where each figure comes from. It also drafts an investment committee memo, and a second agent argues against the deal before anyone can approve it.

I wanted to test one thing: can an assistant help a deal team read a data room without losing track of its sources, and can it catch the inconsistencies a careful analyst would catch? Summarising a PDF is easy. Making sure a revenue figure is the audited one, and noticing when two documents disagree, is the actual work.

To test it I wrote a fictional deal: a fund buying 70% of Alpine Precision Components AG, a Swiss machining supplier. The data room has 37 generated files (contracts, audited accounts, a financial model, board minutes, four scanned pages) and three problems planted on purpose. Every company, person and figure is made up.

![Question, cited answer, memo, challenger, review and approval](docs/demo.gif)

## An example

Ask *"What was audited net revenue in FY2025?"* and you get:

> Income statement for the year ended 31 December 2025 (CHF million): Net revenue, FY2025: 142.3 [1]
>
> [1] `05_audited_financial_statements_FY2025.pdf, p. 2`

The information memorandum says something else. When the memo is drafted, the challenger compares the figures and raises:

> **FY2025 revenue in information memorandum does not match the audited accounts.** The marketing document states FY2025 revenue of CHF 148.6 million [1], but the audited accounts show CHF 142.3 million [2], a gap of CHF 6.3 million (+4.4%). No reconciliation was found in the data room.
>
> [1] `01_information_memorandum.pdf, p. 1` [2] `05_audited_financial_statements_FY2025.pdf, p. 2`

It finds the other two planted problems the same way, without being told where they are: the largest customer can terminate its contract on a change of control (and legal due diligence never reviewed that contract), and the FY2026 leverage covenant has 2.7% headroom. It also raises points outside those three. For example, a handwritten board note, readable only through OCR, says the main product launch slipped by three quarters, while the budget still assumes the old date.

Ask *"What is the CEO's annual salary?"* and it answers "Not found in the data room."

## Run it

You need Python 3.11+, Node 22 and Tesseract. No API keys: the offline mode uses a stub model that answers with the best passage it found.

```bash
make install
make demo     # question, answer, memo, challenger, refused approval, approval
make eval     # writes reports/eval.md
make api      # then `make web` in a second terminal: http://localhost:3000
```

## What worked and what didn't

**Retrieval.** I expected hybrid search with a reranker to beat plain BM25. It didn't. On this data room BM25 reaches recall@10 98.6%, and hybrid + rerank 97.6% with the offline models. With pre-trained ONNX models (`bge-small` embeddings and a MiniLM cross-encoder) hybrid + rerank reaches 98.1% recall@10 and nDCG@10 0.956 against 0.947 for BM25: slightly better ranking, still no recall gain. The questions use the same words as the documents, so there is little left for semantic search to fix. I kept the hybrid pipeline because real data rooms are bigger and messier, but nothing here proves it is better.

**Abstention.** Deciding when to say "not found" is the weakest part. The offline rule is lexical: 3 of the 12 unanswerable questions still get an answer, and 5 of the 105 answerable ones are withheld. A real model's own "insufficient evidence" reply would add a second check, but I have not measured that.

**Numbers and citations.** 94% of answers with a figure contain the right one. 87% of citations point at the chunk the gold set expects.

**OCR and anonymisation.** Tesseract reads the four scans at 99.5–100% character accuracy. None of the ten personal-data strings in the data room reach the search index or survive in the redacted PDFs.

All figures are in [`reports/eval.md`](reports/eval.md). CI regenerates the report and fails if it changed.

## On real documents

The synthetic data room is too small and too clean to trust those scores, so I ran the same code on two public datasets with human labels. Both are downloaded by checksum (`make eval-real`) and not committed.

**FinanceBench** has 150 analyst questions on 84 real SEC filings, with the evidence page marked for each. Searching within the right filing, the best method puts an evidence page in the top 10 about half the time (BM25 53.3%, hybrid + rerank 52.0%), and in the top 5 only 26% of the time for the domain questions. That is far from the 98% on the synthetic data room. Filings are hundreds of pages of near-identical financial tables, and my fast extraction keeps table rows as text lines without their column headers. The stub model cannot do the arithmetic these questions need, so answer quality on real filings is not measured.

**CUAD** has 510 commercial contracts labelled by lawyers. I scored the challenger's change-of-control detector on the 102-contract test split. The patterns I wrote for the synthetic contracts reach F1 0.533 (precision 63%, recall 46%). I rewrote them on the 408 training contracts and scored the test split once: F1 0.622. The challenger only raises an argument when the clause gives a termination right; that narrower rule flags 3 of the 26 contracts with a provision, all correctly.

Both results are in [`reports/eval_real.md`](reports/eval_real.md).

## What is tested and what is only configured

| Part | Status |
| --- | --- |
| Ingestion, retrieval, agents, review rules, MCP server, API | Unit and integration tests, 98% coverage, run in CI |
| Web workspace | Playwright runs the full flow in a browser in CI |
| Postgres + pgvector store | Tested against a real Postgres container in CI |
| Azure Document Intelligence, Azure OpenAI, certificate sign-in | Code written; tested against mocked HTTP responses only |
| Terraform (AKS, private endpoints, Key Vault) and Helm | Pass `terraform validate` and `helm lint`; never deployed |

## Limitations

- The data room is synthetic and small (37 files, 130 chunks), so the scores are higher than on a real one. On real filings retrieval is much weaker (see above).
- Thresholds and the lexical reranker were tuned on the synthetic questions they are scored on. Only the CUAD patterns have a held-out test split.
- With the stub model, the answer metrics measure retrieval and passage selection, not generation.
- The handwritten note is an oblique font with some jitter, not real handwriting.
- The challenger finds the kinds of problems it has checks for. It is not a general fraud detector.

## More

- [docs/architecture.md](docs/architecture.md): modules, how an answer is produced, the challenger checks, the review gate
- [docs/security.md](docs/security.md): anonymisation, certificate authentication, roles, approvals, audit log
- [docs/deployment.md](docs/deployment.md): Terraform and Helm

MIT licence. All data in this repository is synthetic.
