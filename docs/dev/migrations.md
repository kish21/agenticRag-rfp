# Database Migrations (Alembic)

Schema changes are now versioned via Alembic. The raw `schema.sql` is kept as reference but is no longer the source of truth — Alembic migrations are.

## How it works

- On startup, `app/main.py` calls `alembic upgrade head` automatically.
- Migration files live in `alembic/versions/`.
- The DB URL is read from `settings.database_url` (i.e., `DATABASE_URL` in `.env`).

## Making a schema change

1. Create a new migration file:
   ```bash
   python -m alembic revision -m "add_column_foo_to_bar"
   ```
   This creates `alembic/versions/<hash>_add_column_foo_to_bar.py`.

2. Edit the generated file — fill in `upgrade()` and `downgrade()`:
   ```python
   def upgrade():
       op.add_column("bar", sa.Column("foo", sa.Text(), nullable=True))

   def downgrade():
       op.drop_column("bar", "foo")
   ```

3. Apply locally:
   ```bash
   python -m alembic upgrade head
   ```

4. Roll back one step (if needed):
   ```bash
   python -m alembic downgrade -1
   ```

## Useful commands

| Command | What it does |
|---|---|
| `alembic upgrade head` | Apply all pending migrations |
| `alembic downgrade -1` | Roll back one migration |
| `alembic current` | Show current DB revision |
| `alembic history` | Show all migrations |
| `alembic revision -m "description"` | Create a new empty migration |

## Existing databases (bootstrapped with schema.sql)

If your database was created using the raw `schema.sql` before Alembic was added, stamp it at the baseline revision so Alembic knows the schema is already in place:

```bash
python -m alembic stamp 0001
```

This tells Alembic "this DB is already at revision 0001" without re-running the DDL.
