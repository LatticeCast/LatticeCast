# E2E

```text
browser trigger -> controller -> API -> RLS/DB write -> API/DB read
-> store refresh -> rendered changed state
```

- Every mutation proves persisted data and UI after navigation/reload; HTTP 200,
  toast, and local state are insufficient.
- Reuse `e2e/conftest.py` and `e2e/e2e_base.py`; isolated fixture data must be
  cleaned up. Wait on responses, locators, URLs, or derived state—never sleep.
- Run focused test, then affected suite:
  `docker compose --profile test up -d browser e2e`
  `docker compose --profile test exec e2e pytest tables/test_column_doc_type.py -v`
- `--snapshot` writes `/output/*.png` in browser and `.browser/*.png` on host.
  Inspect the image for every UI/layout change.
