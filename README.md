# Climate-FCV Country Evidence Bank

This public companion repository holds structured, reviewable country evidence for the Climate-FCV screening app. It keeps source metadata, atomic evidence, pathways, review decisions, country dossiers, and approved runtime releases separate from the application code.

## Status and disclaimer

This is an analytical evidence resource, not an official World Bank product, policy position, country classification, or operational decision tool. It supports human analysis and review; it does not replace professional judgement or relevant institutional processes.

## Evidence method

Evidence records will identify a public source, capture a concise atomic claim, preserve traceable metadata, and link claims to defined Climate-FCV pathways. Review decisions will document whether evidence is suitable for inclusion. Country dossiers and runtime releases will contain only human-approved, derived summaries.

## Review and release workflow

1. Add public-source metadata and atomic evidence records.
2. Link evidence to pathways and prepare review decisions.
3. A designated human reviewer approves or rejects material for a dossier.
4. Only approved dossier content is assembled into a versioned runtime release.

No runtime release is authoritative until the planned human review gate has been completed.

## Public-content and copyright boundary

Store metadata, short quotations where permitted, and original derived summaries only. Do not commit source PDFs, copyrighted source-document copies, secrets, credentials, restricted OPCS material, or model self-citations. Do not redistribute any PDF without permission from the rights holder. Local source documents belong in the ignored `source_documents/` directory.

## Public repository setup

Create a Python 3.11+ environment and install development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the repository contract test:

```powershell
python -m pytest tests/test_repository_contract.py -q -p no:cacheprovider
```
