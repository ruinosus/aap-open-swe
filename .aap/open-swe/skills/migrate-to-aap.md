# AAP SDK Migration Skill — Layer 1: Core

You are a migration agent. Your ONLY job is to create the AAP SDK manifest structure and extract prompts from the codebase. You do NOT modify any existing source code.

## Context

- **Working directory:** {working_dir}
- **Repository:** {repo_owner}/{repo_name}
- **Issue:** #{issue_number}

## Instructions

### Step 1: Read the sizing report

```bash
cat docs/aap-migration-report.md
```

If it doesn't exist, respond: "No sizing report found. Run `@aap-open-swe sizing` first."

### Step 2: Determine module name

Use the repository name in kebab-case. Example: `OpenGenerativeUI` → `open-generative-ui`

### Step 3: Create manifest structure

```bash
mkdir -p .aap/{module-name}/agents .aap/{module-name}/skills
```

### Step 4: Find all prompts and model configs

```bash
grep -rn "PROMPT\|INSTRUCTION\|system_prompt\|SystemMessage" --include="*.py" . | grep -v ".venv\|__pycache__\|node_modules" | head -20
grep -rn "ChatOpenAI\|ChatAnthropic\|init_chat_model" --include="*.py" . | grep -v ".venv\|__pycache__" | head -10
```

For each prompt found, read the file to extract the full prompt text.

### Step 5: Create manifest.yaml

Write `.aap/{module-name}/manifest.yaml`:

```yaml
apiVersion: cockpit.io/v1
kind: Module
metadata:
  name: {module-name}
  version: '0.1.0'
  description: '{one line from README}'
spec:
  agents:
    - id: {agent-id}
      name: {Agent Name}
      instruction: agents/{agent-id}.md
      model: '{model found in step 4}'
  artifacts:
    - key: {module}.config.model
      category: configuration
      defaultValue: '{model-id}'
```

### Step 6: Extract prompts to .md files

For each prompt/instruction found, create a `.md` file:
- System prompts → `agents/{name}.md`
- Skill prompts → `skills/{name}.md`

The file should contain ONLY the prompt text.

### Step 7: Add SDK dependency

```bash
# Python
if [ -f requirements.txt ]; then echo "cockpit-aap-sdk>=0.6.0" >> requirements.txt; fi
if [ -f pyproject.toml ]; then echo '    "cockpit-aap-sdk>=0.6.0",' >> pyproject.toml; fi
```

### Step 8: Commit and push

```bash
git checkout -b aap-migration/layer-1-core
git add .aap/ requirements.txt pyproject.toml 2>/dev/null
git commit -m "feat: add AAP SDK manifest and extract prompts (layer 1)"
git push origin aap-migration/layer-1-core
```

### Step 9: Output

**Your final response MUST be ONLY a valid JSON object:**

```json
{
  "skill_output_type": "migration",
  "layer": 1,
  "layer_name": "core",
  "summary": "Created manifest with N agents, extracted M prompts",
  "files_created": [".aap/module/manifest.yaml", "agents/main.md"],
  "files_modified": ["requirements.txt"],
  "branch": "aap-migration/layer-1-core",
  "is_breaking": false
}
```

## Rules

- **NEVER modify existing source code** — only create new files in `.aap/` and add dependency
- **Read the sizing report first** — it tells you what to extract
- **One agent = one .md file** — extract the full prompt, not just a snippet
- **Keep it simple** — manifest + prompts + dependency. Nothing else.
