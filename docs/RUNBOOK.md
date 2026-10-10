# Runbook

Operating notes for this repository: local setup, configuration, deployment, database migrations, secrets, model settings, the cost ledger, and rollback.

Real project identifiers, hosts and account names are never written here. Placeholders in angle brackets stand for them: `<PROJECT_ID>`, `<REGION>`, `<NEON_PROJECT>`, `<OWNER>/<REPO>`.

## 1. Local setup

You need Python 3.11 or 3.12 (`requires-python` in `pyproject.toml`), [`uv`](https://docs.astral.sh/uv/), and Node.js for the CSS build.

```bash
uv sync --frozen        # Python dependencies, exactly as locked in uv.lock
npm ci                  # Tailwind build tooling only
npm run build:css       # regenerates src/web/static/app.css, which is committed
```

Copy `.env.example` to `.env` and fill it in. `.env` is git-ignored. A local run needs the variables in §2 and a development database.

```bash
uv run alembic upgrade head          # development database only
uv run uvicorn src.web.main:app --reload
```

Run the same checks CI runs:

```bash
uv run ruff check src tests scripts
uv run pytest -q
```

The test suite is offline. It stubs the model provider and uses an in-memory database, so it needs no `DATABASE_URL` and no API key.

Never point a local run at the production database.

## 2. Configuration

Settings are read from the environment. Values come from `.env` locally and from Secret Manager in production. Names only are listed here.

| Variable | Purpose |
|---|---|
| `ENV` | Environment name. The deploy sets `production`. |
| `DATABASE_URL` | Postgres connection string. A secret in production. |
| `SESSION_SECRET` | Signs session cookies. A secret in production. |
| `SESSION_MAX_AGE` | Session lifetime. |
| `OPENROUTER_API_KEY` | Model provider key. A secret in production. |
| `OPENROUTER_MODEL` | Model identifier, for example `google/gemini-3.8-flash`. |
| `OPENROUTER_REASONING_EFFORT` | Reasoning effort. Defaults to `low`; the private app runs `low`. |
| `OPENROUTER_TIMEOUT_SECONDS` | Timeout per model request. Defaults to 60. |
| `UI_DEFAULT_LANG` | Default interface language. |
| `GCP_PROJECT_ID`, `GCP_REGION` | Deployment targets, used by the workflow. |
| `PROD_DB_HOST_FRAGMENT` | Operator scripts only (not the app): a fragment of the production host name. Set it in your local `.env`. While it is unset or empty, the scripts refuse every non-local database. |

## 3. Deployment

The pipeline is `.github/workflows/deploy.yml`.

1. It starts on a push to `master` that changes `src/**`, `pyproject.toml`, `uv.lock`, `Dockerfile` or the workflow file, and on manual dispatch.
2. The **test** job runs `uv sync --frozen`, then `ruff`, then `pytest`.
3. The **deploy** job runs only after the tests pass. It authenticates to Google Cloud with **Workload Identity Federation**, so no key file exists anywhere. It builds an image tagged with the commit SHA, pushes it to Artifact Registry, deploys it to Cloud Run, and prints the service URL.
4. Deploys are serialised. A queued run waits for the one in flight, because an interrupted deploy leaves the service on a half-updated revision.

**Repository secrets** (GitHub Actions settings), set once: `GCP_PROJECT_ID`, `GCP_REGION`, `WIF_PROVIDER` (the Workload Identity provider's resource name) and `WIF_SERVICE_ACCOUNT`. The provider's attribute condition must name this repository.

**Cloud Run settings** come from the workflow: 0 to 2 instances, 1 vCPU, 512 MiB, a 300-second request timeout, and a runtime service account separate from the deploying one. The model and effort are set in the deploy command, not in the code.

**First-time setup** (once per project): create the Artifact Registry repository `atsker` in `<REGION>`; create the Workload Identity pool and provider for this repository; create the deployer and runtime service accounts; and create the three Secret Manager secrets listed in §6. The first deploy creates the Cloud Run service.

Migrations are **not** run by CI. They are applied by hand, in the order given in §4.

## 4. Database migrations

- Every schema change is an Alembic migration. No environment gets manual DDL.
- Migrations are **additive** in a release: new tables and new columns, with a default or as nullable. Renames and drops wait for a later release, after no running code uses the old name.
- **Expand, then contract.** The first release adds the new shape; the code that uses it ships afterwards; the old shape is removed only when nothing reads it.
- For a release whose new code reads or writes a new column, the order is:
  1. take a snapshot of the production database (§5);
  2. apply the migration to production;
  3. confirm the code already running still works against the new schema, which it should, since it ignores the new columns;
  4. push the code that uses the new column. The push deploys it.
- Never push code that writes a new column before the migration has reached production. The pipeline deploys on push, so the migration must come first.
- Apply a migration only with the `DATABASE_URL` of the database you mean to change. Development first.

## 5. Snapshots

Before any production migration, take a snapshot of the Neon project (`<NEON_PROJECT>`) in the Neon console, or create a branch from the current state. Write the snapshot's name in the release note. A snapshot is the only way back from a bad data migration (§9).

## 6. Secrets

- Three secrets live in Secret Manager: the model provider key, the database URL and the session secret. Cloud Run reads them at `:latest`.
- Add a new version **from a file**, never by piping the value into a command:
  `gcloud secrets versions add <SECRET_NAME> --data-file=<path> --project <PROJECT_ID>`.
  Delete the file afterwards. A pipe leaves the value in shell history.
- A new version applies to revisions started after it is added. Deploy again to be sure.
- Nothing secret is committed. `.env` and `.neon` are git-ignored. `.env.example` holds placeholders only. Keys and connection strings never appear in code, tests, comments, logs or workflow files.

## 7. Model settings and the answer cache

- **Model and effort:** `OPENROUTER_MODEL` and `OPENROUTER_REASONING_EFFORT`. Change them in the deploy command, in one commit, with the reason in the commit message. The private app runs `google/gemini-3.8-flash` at `low`.
- **Per-model request fields:** `src/extract/model_params.json` maps a model identifier to the request fields that must be left out for that model. It is a data file. An empty object means nothing is left out.
- **The cache:** every model call is cached under a key made of the purpose, the prompt version, the model, the effort and the input. A repeated analysis is served from the cache and costs nothing. Changing the model or the effort therefore never serves an old answer. Changing a prompt means bumping its version.

## 8. Cost ledger and purging a cached answer

Every uncached model call writes one row to the `llm_calls` table: model, purpose, tokens, cost and latency. `scripts/llm_costs.py` reads it.

```bash
uv run python scripts/llm_costs.py list                             # recent calls
uv run python scripts/llm_costs.py summary                          # totals by model and purpose
uv run python scripts/llm_costs.py purge --hash <sha256>            # dry run: shows the rows
uv run python scripts/llm_costs.py purge --hash <sha256> --confirm  # marks them
```

`purge` marks the rows with that content hash so they are never served from the cache again. It is a dry run until `--confirm` is given. Use it for a wrong or unwanted answer.

The evaluation scripts make paid model calls. Run them against the development database. `scripts/judge_stability.py` refuses the production host unless `--prod` is passed, and asks for confirmation before it spends anything. All three guarded scripts (`judge_stability.py`, `letters_import.py`, `golden_run.py`) recognise the production host by `PROD_DB_HOST_FRAGMENT`; without that variable they refuse every non-local database, so set it in your local `.env` before running them.

## 9. Rollback

- **Code.** Revert the merge commit on `master` with `git revert -m 1 <merge-commit>` and push. The push runs the pipeline, which deploys the reverted code. Additive schema changes can stay; the older code ignores them.
- **Faster, without a commit.** Cloud Run keeps earlier revisions. When the code is fine but the latest revision is not, moving traffic back to a previous revision is the quickest fix: `gcloud run services update-traffic`.
- **Data.** Nothing rolls data back on its own. A bad data migration is undone by restoring the snapshot taken in §5, which discards every write made after it.
