# PM Layer

PM is a generic table template, not a PM-specific persistence/API layer.

- `POST /tables/template/pm` seeds the schema and views; SQL seeders define exact fields/options.
- Ticket hierarchy uses the per-table `row_id`; keys are derived from type + row ID.
- Detailed ticket content belongs in the row's doc blob cell, not a separate PM model.
- Keep PM conventions in templates/UI; generic table behavior stays generic.
