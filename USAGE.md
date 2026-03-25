# Usage Guide

## Invoke the agent via GitHub issues

You can trigger the agent by mentioning `@aap-open-swe` in an issue, issue comment, or PR comment.

### Basic usage

- **Issue body or title**: add `@aap-open-swe` to ask the agent to work on the issue.
- **Issue comment**: mention `@aap-open-swe` and describe the task.
- **PR comment**: mention `@aap-open-swe` to request changes on the PR branch.

### Available skills

Use a skill keyword right after the mention:

| Skill | Trigger | What it does | Example |
|---|---|---|---|
| Code review | `@aap-open-swe review` | Reviews the PR diff and leaves inline feedback | `@aap-open-swe review check for edge cases and naming` |
| Security scan | `@aap-open-swe security` | Scans the PR diff for security issues | `@aap-open-swe security look for injection and secret leaks` |
| Doc generator | `@aap-open-swe docs` | Updates or creates documentation after changes land | `@aap-open-swe docs update README and architecture docs` |
| Test generator | `@aap-open-swe tests` | Generates tests for low-coverage code | `@aap-open-swe tests add coverage for the parser` |
| Project docs | `@aap-open-swe project-docs` | Updates project markdown files such as README and guides | `@aap-open-swe project-docs refresh usage docs` |
| Sizing | `@aap-open-swe sizing` | Analyzes the repository and produces a sizing report | `@aap-open-swe sizing assess migration effort` |
| Migrate to AAP | `@aap-open-swe migrate` | Helps migrate a repository to the AAP structure | `@aap-open-swe migrate prepare the repo for AAP SDK` |
| Respond review | `@aap-open-swe respond-review` | Responds to review comments after fixes are made | `@aap-open-swe respond-review reply to addressed review comments` |

### Examples

```text
@aap-open-swe review please inspect the PR for correctness and style issues
```

```text
@aap-open-swe security look for unsafe file handling, secrets, and injection risks
```

```text
@aap-open-swe docs update the usage instructions after the API change
```

```text
@aap-open-swe tests add coverage for the new retry behavior
```

```text
@aap-open-swe project-docs refresh the README and USAGE guide with the new workflow
```

```text
@aap-open-swe sizing estimate the work required for this repository migration
```

```text
@aap-open-swe migrate prepare this repo for AAP SDK configuration
```

```text
@aap-open-swe respond-review address the remaining review comments
```

## Automatic triggers on pull requests

The repository has an automatic PR workflow in `.github/workflows/agent.yml`.

When a PR is **opened** or **synchronized**, the workflow runs both:

1. **Code review**
2. **Security scan**

Both skills run automatically without any manual mention. Their purpose is to review the diff, post inline comments, and surface actionable findings as soon as the PR changes.

## Execution report format

When the agent finishes, it posts an execution report back to the issue, PR, or thread.

Typical fields in the report:

- **`skill_output_type`** — identifies the output family, such as `review`, `pr`, `migration`, or `sizing`.
- **`summary`** — short human-readable summary of the work completed.
- **`score`** — review quality score in `N/10` format for review-oriented skills.
- **`comments`** — list of findings, usually including file, line, severity, and message.
- **`suggested_guardrails`** — security-focused guardrails that can prevent similar issues in the future.
- **`files_changed`** — files created or modified by the agent for PR-generating skills.
- **`branch`** — branch name used for the generated changes.
- **`repo_url`** — repository analyzed for sizing or migration tasks.
- **`repo_type`** — whether the analyzed repository was `internal` or `external`.
- **`languages`** — languages detected during sizing or migration analysis.
- **`total_findings`** — total number of findings produced by a sizing run.
- **`findings`** — detailed repository findings with category, impact, and code snippet.
- **`layers`** — per-layer summaries for sizing work.
- **`proposed_structure`** — suggested `.aap/` file layout for migration work.
- **`layer`** / **`layer_name`** — migration layer that was executed.
- **`files_created`** / **`files_modified`** — migration outputs broken down by file status.
- **`is_breaking`** — indicates whether the change is breaking.

The exact shape varies by skill, but the report always summarizes what happened, what files were touched, and what follow-up action is needed.

## Model configuration

The model is configured with the `OPEN_SWE_MODEL` environment variable.

### Examples

```bash
OPEN_SWE_MODEL=openai:gpt-4o
OPEN_SWE_MODEL=anthropic:claude-sonnet-4-6
OPEN_SWE_MODEL=google_genai:gemini-2.5-pro
```

### Behavior

- If `OPEN_SWE_MODEL` is set, the agent uses that model identifier.
- If it is not set, workflows and local development fall back to the repository default.
- The GitHub workflow uses `OPEN_SWE_MODEL` from repository variables when available.

### Provider keys

Set the matching API key for the provider you choose:

- `OPENAI_API_KEY` for OpenAI models
- `ANTHROPIC_API_KEY` for Anthropic models
- `GOOGLE_API_KEY` for Google models

## Related files

- `README.md` — project overview and quick start
- `.github/workflows/agent.yml` — automatic GitHub issue and PR triggers
- `.env.example` — environment variable reference
