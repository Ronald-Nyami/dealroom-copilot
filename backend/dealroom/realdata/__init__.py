"""Evaluation on real public data: FinanceBench (SEC filings) and CUAD (commercial contracts).

The raw documents are not committed. ``fetch`` downloads them from the URLs pinned in
``data/real/manifest.json`` and refuses any file whose SHA-256 does not match.
"""
