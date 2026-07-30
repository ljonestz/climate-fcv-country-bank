# Climate-FCV Country Evidence Bank Guidance

## Purpose and architecture

This is a public companion repository for structured Climate-FCV country evidence. It will contain source metadata, atomic evidence, pathways, review decisions, country dossiers, and approved runtime releases. The `schemas/` directory defines public data contracts; `climate_bank/` will hold supporting validation, release, and dossier logic; `scripts/` will hold repository utilities.

## Local commands

Install development dependencies:

```powershell
C:/WBG/Python313/python.exe -m pip install -r requirements-dev.txt
```

Run the contract test:

```powershell
C:/WBG/Python313/python.exe -m pytest tests/test_repository_contract.py -q -p no:cacheprovider
```

## Public-content boundary

Commit only public-source metadata, permitted short excerpts, and original derived summaries. Never commit source PDFs, secrets, credentials, restricted OPCS material, unpermitted copyrighted reproductions, or model self-citations. Keep any local source documents in the ignored `source_documents/` directory.

## Branch workflow

Keep `main` stable. Make substantive changes on a descriptive feature branch, verify the relevant tests, and review staged changes before committing. Do not commit directly to `main` after this initial scaffold.

## Human approval gate

Evidence, dossiers, and runtime releases require designated human review before they are treated as approved. Automation may prepare or validate records, but it must not bypass or imply that review decision.
