# E2E

`e2e/` is pytest + requests + remote Playwright against the real stack.

```bash
docker compose --profile test up -d browser e2e
docker compose --profile test exec e2e pytest tables/test_column_doc_type.py -v
```

- Reuse fixtures/helpers in `e2e/conftest.py` and `e2e/e2e_base.py`; each test creates isolated data.
- Assert API and final rendered state. Synchronize on responses, locators, URLs, or derived UI—never `sleep`.
- Run focused test first, then affected package/suite. Snapshot artifacts are in `.browser/`.
