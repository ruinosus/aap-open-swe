"""Standalone agent runner for GitHub Actions.

Runs the Open SWE agent without LangGraph server — direct Deep Agent invocation.
Uses the GitHub Actions runner as the sandbox (SANDBOX_TYPE=local).
"""

import asyncio
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("run_standalone")


def _format_sizing_markdown(agent_response: str) -> str:
    """Format sizing JSON output as rich markdown for GitHub issue comments."""
    data = None
    try:
        parsed = json.loads(agent_response)
        if isinstance(parsed, list):
            for block in parsed:
                if isinstance(block, dict) and block.get("text"):
                    try:
                        data = json.loads(block["text"])
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue
        elif isinstance(parsed, dict) and parsed.get("skill_output_type"):
            data = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    if not data or data.get("skill_output_type") != "sizing":
        return agent_response

    layer_emoji = {
        1: "\U0001f9f1",
        2: "\U0001f527",
        3: "\U0001f3a8",
        4: "\U0001f6e1\ufe0f",
        5: "\u2728",
        6: "\U0001f4bb",
    }
    impact_emoji = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
    lines = []

    lines.append("## \U0001f4ca AAP SDK Migration \u2014 Sizing Report")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Repository** | {data.get('repo_url', 'N/A')} |")
    repo_type = data.get("repo_type", "unknown")
    type_label = (
        "\U0001f500 External (fork required)" if repo_type == "external" else "\U0001f3e0 Internal"
    )
    lines.append(f"| **Type** | {type_label} |")
    lines.append(f"| **Languages** | {', '.join(data.get('languages', []))} |")
    lines.append(f"| **Total Findings** | **{data.get('total_findings', 0)}** |")
    lines.append("")

    layers = data.get("layers", [])
    if layers:
        lines.append("### Layers")
        lines.append("")
        lines.append("| Layer | Name | Findings | Breaking? |")
        lines.append("|-------|------|----------|-----------|")
        for la in layers:
            num = la.get("layer", 0)
            emoji = layer_emoji.get(num, "\U0001f4e6")
            name = la.get("name", "")
            count = la.get("count", la.get("findings_count", 0))
            breaking = "\u26a0\ufe0f Yes" if la.get("is_breaking") else "\u2705 No"
            lines.append(f"| {emoji} {num} | **{name}** | {count} | {breaking} |")
        lines.append("")

    findings = data.get("findings", [])
    if findings:
        lines.append("<details>")
        lines.append(f"<summary>\U0001f4cb Detailed Findings ({len(findings)})</summary>")
        lines.append("")
        lines.append("| # | Layer | Impact | File | Description |")
        lines.append("|---|-------|--------|------|-------------|")
        for i, f in enumerate(findings):
            imp = f.get("impact", "low")
            ie = impact_emoji.get(imp, "\u26aa")
            fp = f.get("file_path", f.get("file", "")).replace("/tmp/aap-sizing-target/", "")
            desc = (f.get("title", "") or f.get("rationale", "") or f.get("description", ""))[:80]
            lines.append(f"| {i + 1} | L{f.get('layer', '?')} | {ie} {imp} | `{fp}` | {desc} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    proposed = data.get("proposed_structure", [])
    if proposed:
        lines.append("<details>")
        lines.append(
            f"<summary>\U0001f4c1 Proposed .aap/ Structure ({len(proposed)} files)</summary>"
        )
        lines.append("")
        lines.append("```")
        for p in proposed:
            lines.append(p)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("### Next Steps")
    lines.append("")
    lines.append("```")
    lines.append("@aap-open-swe migrate --layer=core        # \U0001f9f1 Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=tools       # \U0001f527 Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=frontend    # \U0001f3a8 \u26a0\ufe0f BREAKING")
    lines.append("@aap-open-swe migrate --layer=governance  # \U0001f6e1\ufe0f Safe, non-breaking")
    lines.append("@aap-open-swe migrate --layer=polish      # \u2728 Safe, non-breaking")
    lines.append(
        "@aap-open-swe migrate --layer=code        # \U0001f4bb \u26a0\ufe0f BREAKING (refactors source)"
    )
    lines.append("```")

    return "\n".join(lines)


async def run_agent(task: str, repo_dir: str, repo_owner: str, repo_name: str, issue_number: int):
    """Run the SWE agent on a task, then commit + open PR + comment."""
    from deepagents import create_deep_agent
    from deepagents.backends import LocalShellBackend

    from agent.aap_config import (
        get_agent_instruction,
        get_manifest,
        get_model_id,
        get_model_max_tokens,
        get_model_temperature,
        get_skill_instruction,
    )
    from agent.observability import (
        ProgressReporter,
        build_execution_report,
        gh_group,
        gh_notice,
        write_step_summary,
    )
    from agent.observability.streaming_callback import create_callbacks
    from agent.utils.model import make_model

    _start_time = time.time()

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        logger.error("GITHUB_TOKEN not set")
        sys.exit(1)

    # Handle respond-review skill — no agent needed, just reply to PR comments
    skill_id = os.environ.get("SKILL_ID", "")
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    if skill_id == "respond-review" and pr_number:
        from agent.review_responder import respond_to_review

        logger.info("Responding to review comments on PR #%d", pr_number)
        stats = respond_to_review(repo_owner, repo_name, pr_number, github_token, repo_dir)
        logger.info("Review response stats: %s", json.dumps(stats))
        agent_response = f"Responded to {stats.get('replied', 0)} review comments ({stats.get('skipped', 0)} skipped, {stats.get('already_replied', 0)} already replied)."

        github_output = os.environ.get("GITHUB_OUTPUT", "")
        if github_output:
            with open(github_output, "a") as f:
                f.write("has_changes=false\n")
                f.write("branch_name=\n")
                f.write(
                    f"agent_response<<AGENT_RESPONSE_EOF_7f3c9a\n{agent_response}\nAGENT_RESPONSE_EOF_7f3c9a\n"
                )
        else:
            print(
                json.dumps(
                    {"has_changes": False, "branch_name": "", "agent_response": agent_response}
                )
            )
        return {"has_changes": False, "branch_name": "", "agent_response": agent_response}

    # Initialize progress reporter for live issue comment updates
    progress = ProgressReporter(
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        issue_number=issue_number,
        comment_id=int(os.environ.get("PROGRESS_COMMENT_ID", "0")) or None,
        source_repo=os.environ.get("SOURCE_ISSUE_REPO", f"{repo_owner}/{repo_name}"),
        skill_id=skill_id,
        model_id="",  # Set after model loading
    )

    with gh_group("Sandbox setup"):
        # Create local sandbox pointing at the cloned repo.
        # virtual_mode=True restricts file operations to root_dir, preventing
        # the agent from scanning system directories like /proc.
        sandbox = LocalShellBackend(root_dir=repo_dir, inherit_env=True, virtual_mode=True)

        # Configure git identity
        sandbox.execute("git config user.name 'aap-open-swe[bot]'")
        sandbox.execute("git config user.email 'aap-open-swe@users.noreply.github.com'")

    with gh_group("Model loading"):
        # Load model from manifest
        model_id = get_model_id()
        model = make_model(
            model_id,
            temperature=get_model_temperature(),
            max_tokens=get_model_max_tokens(),
        )
        gh_notice(f"Model: {model_id}")
        progress.model_id = model_id

    with gh_group(f"System prompt — {skill_id or 'swe-coder'}"):
        # Build system prompt — skill overrides base if specified
        if skill_id and skill_id not in ("swe-coder", ""):
            skill_instruction = get_skill_instruction(skill_id)
            if skill_instruction:
                # Use simple string replace instead of .format() to avoid
                # conflicts with JSON curly braces in skill instructions
                system_prompt = (
                    skill_instruction.replace("{working_dir}", repo_dir)
                    .replace("{repo_owner}", repo_owner)
                    .replace("{repo_name}", repo_name)
                    .replace("{pr_number}", str(pr_number))
                    .replace("{issue_number}", str(issue_number))
                )
            else:
                logger.warning("Skill %s not found, falling back to swe-coder", skill_id)
                skill_id = ""  # fall through to default
                system_prompt = ""

        if not skill_id or skill_id == "swe-coder":
            # Default swe-coder behavior
            manifest_instruction = get_agent_instruction()
            if manifest_instruction:
                system_prompt = manifest_instruction.format(
                    working_dir=repo_dir,
                    linear_project_id="",
                    linear_issue_number="",
                    agents_md_section="",
                )
            else:
                system_prompt = (
                    f"You are a coding assistant. Your working directory is {repo_dir}. "
                    "Use the execute tool to run commands. Be concise and focused."
                )

        # Add GitHub Actions context to the prompt
        system_prompt += f"""

---

### GitHub Actions Context

You are running inside a GitHub Actions workflow on repository {repo_owner}/{repo_name}.
Issue/PR number: #{issue_number}

When you are done with your changes:
1. Run linters/formatters if available
2. Stage and commit your changes with a descriptive message
3. Push to a new branch named `aap-open-swe/issue-{issue_number}`
4. The workflow will handle creating the PR and commenting on the issue.

Do NOT call commit_and_open_pr or github_comment tools — they are not available here.
Use the execute tool for all git operations.
"""
        gh_notice(f"Skill: {skill_id or 'swe-coder'}, prompt: {len(system_prompt)} chars")

    # Build response_format for review-type skills (structured output).
    # PR-type skills (doc-generator, test-generator, project-docs) need tool
    # calling to execute git commands, so they must NOT use response_format
    # which forces immediate JSON return without tool use.
    response_format = None
    review_skills = ("code-review", "security-scan")
    if skill_id in review_skills:
        try:
            from langchain.agents.structured_output import ProviderStrategy

            from agent.schemas import SKILL_SCHEMAS

            schema = SKILL_SCHEMAS.get(skill_id)
            if schema:
                response_format = ProviderStrategy(schema=schema, strict=True)
                logger.info("Using structured output schema: %s", schema.__name__)
        except Exception:
            logger.warning(
                "Could not set up structured output, falling back to free-form", exc_info=True
            )

    # Build middleware stack
    middleware = []
    try:
        from cockpit_aap import create_guardrail_middleware

        guardrail_mw = create_guardrail_middleware(
            get_manifest(),
            include_builtin_pii=True,
        )
        middleware.append(guardrail_mw)
        logger.info("Added SDK guardrail middleware (manifest + PII)")
    except Exception:
        logger.warning("Could not create SDK guardrail middleware", exc_info=True)

    # Repository protection — blocks pushes to repos outside ALLOWED_GITHUB_ORGS.
    # External repos MUST be forked first. This is a critical safety guardrail.
    from agent.aap_config import get_allowed_github_orgs
    from agent.middleware.repo_protection import create_repo_protection_middleware

    repo_protection_mw = create_repo_protection_middleware(
        allowed_orgs=get_allowed_github_orgs(),
        current_repo_owner=repo_owner,
        current_repo_name=repo_name,
    )
    if repo_protection_mw:
        middleware.append(repo_protection_mw)
        logger.info("Added repo protection guardrail (whitelist: %s)", get_allowed_github_orgs())

    # Output validation (JSON structure) — kept as custom middleware
    # since JSON schema validation has no equivalent in the SDK
    if skill_id and skill_id not in ("swe-coder", ""):
        from agent.middleware.output_validator import create_output_validator

        output_mw = create_output_validator(skill_id)
        if output_mw:
            middleware.append(output_mw)

    # Add ensure_no_empty_msg middleware for skills that use tools.
    # This is the key insight from the original Open SWE: it forces the agent
    # to ALWAYS call a tool on every turn, preventing early JSON-only returns.
    pr_skills = ("doc-generator", "test-generator", "project-docs", "migrate-to-aap")
    analysis_skills = ("aap-sizing",)
    use_default_tools = skill_id in pr_skills or skill_id in analysis_skills

    if use_default_tools:
        from agent.middleware.ensure_no_empty_msg import ensure_no_empty_msg

        middleware.append(ensure_no_empty_msg)
        logger.info("Added ensure_no_empty_msg middleware (forces tool usage)")

    with gh_group(f"Middleware stack ({len(middleware)} layers)"):
        logger.info("Creating agent with model=%s, middleware=%d", model_id, len(middleware))

        agent = create_deep_agent(
            model=model,
            system_prompt=system_prompt,
            **({} if use_default_tools else {"tools": []}),
            backend=sandbox,
            response_format=response_format,
            middleware=middleware if middleware else None,
        )

    logger.info("Sending task to agent: %s", task[:200])

    # Set recursion_limit high enough for multi-step tasks.
    # Original Open SWE uses 1000. A 5-layer migration may need 50+ turns.
    from agent.aap_config import get_recursion_limit

    invoke_config = {"recursion_limit": get_recursion_limit()}
    logger.info("Recursion limit: %d", invoke_config["recursion_limit"])

    # Create callbacks: langchain UsageMetadataCallbackHandler + our log groups
    callbacks, token_stats = create_callbacks(progress_reporter=progress, model_id=model_id)
    invoke_config["callbacks"] = callbacks

    progress.start_phase(f"Agent ({skill_id or 'swe-coder'})")

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": task}]},
        config=invoke_config,
    )

    progress.complete_phase(f"Agent ({skill_id or 'swe-coder'})")

    messages = result.get("messages", [])
    ai_messages = [
        m
        for m in messages
        if hasattr(m, "content") and getattr(m, "type", "") == "ai" and m.content
    ]

    # Get agent's last response
    agent_response = ""
    if ai_messages:
        last = ai_messages[-1].content
        agent_response = last if isinstance(last, str) else json.dumps(last, indent=2)

    # Check for structured_response (from response_format / ProviderStrategy)
    structured_response = result.get("structured_response")
    if structured_response:
        logger.info("Got structured_response from agent")
        if hasattr(structured_response, "model_dump"):
            # Pydantic model — convert to dict/JSON
            structured_data = structured_response.model_dump()
            agent_response = json.dumps(structured_data, indent=2)
        elif isinstance(structured_response, dict):
            structured_data = structured_response
            agent_response = json.dumps(structured_data, indent=2)
        else:
            structured_data = None
    else:
        structured_data = None

    logger.info("Agent finished with %d messages", len(messages))

    # Post review if skill is review-type
    if skill_id in ("code-review", "security-scan") and pr_number:
        from agent.review_poster import parse_review_output, post_pr_review

        # Prefer structured_data if available, else parse from free-form text
        review = None
        if structured_data and structured_data.get("skill_output_type") == "review":
            review = structured_data
            logger.info("Using structured_response for review posting")
        else:
            review = parse_review_output(agent_response)

        if review:
            post_pr_review(repo_owner, repo_name, pr_number, review, skill_id)
        else:
            logger.warning("Could not parse structured review from agent output")

    # Check if agent made changes — multiple strategies since the agent
    # may have already committed, or even pushed to a different branch.
    diff_result = sandbox.execute("git diff --stat HEAD")
    staged_result = sandbox.execute("git diff --cached --stat")
    status_result = sandbox.execute("git status --porcelain")

    has_uncommitted = bool(
        (diff_result.output and diff_result.output.strip())
        or (staged_result.output and staged_result.output.strip())
        or (status_result.output and status_result.output.strip())
    )

    # Also check if agent created commits ahead of origin (already committed)
    current_branch = sandbox.execute("git rev-parse --abbrev-ref HEAD")
    current_branch_name = current_branch.output.strip() if current_branch.output else ""
    unpushed = sandbox.execute(f"git log origin/{current_branch_name}..HEAD --oneline 2>/dev/null")
    has_unpushed = bool(unpushed.output and unpushed.output.strip())

    has_changes = has_uncommitted or has_unpushed

    # Use skill-specific branch names
    skill_branch_names = {
        "aap-sizing": "aap-migration/sizing",
        "migrate-to-aap": "aap-migration/full",
    }
    branch_name = skill_branch_names.get(
        skill_id, current_branch_name or f"aap-open-swe/issue-{issue_number}"
    )

    if has_changes:
        progress.start_phase("Push & PR")
        # Validate push target against org whitelist BEFORE pushing
        allowed_orgs = get_allowed_github_orgs()
        if allowed_orgs and repo_owner.lower() not in allowed_orgs:
            logger.error(
                "BLOCKED: Cannot push to %s/%s — org '%s' not in ALLOWED_GITHUB_ORGS (%s)",
                repo_owner,
                repo_name,
                repo_owner,
                ", ".join(sorted(allowed_orgs)),
            )
            has_changes = False
        else:
            if has_uncommitted:
                # Uncommitted changes — commit them
                sandbox.execute("git add -A")
                sandbox.execute(f'git commit -m "fix: address issue #{issue_number}"')

            if branch_name == "main" or branch_name == "master":
                # Don't push to main — create a feature branch
                branch_name = f"aap-open-swe/issue-{issue_number}"
                sandbox.execute(f"git checkout -b {branch_name}")

            push_result = sandbox.execute(
                f"git push https://x-access-token:{github_token}@github.com/{repo_owner}/{repo_name}.git HEAD:refs/heads/{branch_name} --force"
            )

            if push_result.exit_code != 0:
                logger.error("Push failed: %s", push_result.output)
                has_changes = False

        progress.complete_phase("Push & PR")

    # Format sizing reports as rich markdown before output
    if skill_id == "aap-sizing":
        agent_response = _format_sizing_markdown(agent_response)

    # Build execution report first, then finalize progress with it
    progress.update_tokens(
        input_tokens=token_stats.input_tokens,
        output_tokens=token_stats.output_tokens,
        llm_calls=token_stats.llm_calls,
        estimated_cost=token_stats.estimated_cost,
    )

    execution_report = build_execution_report(
        skill_id=skill_id or "swe-coder",
        model_id=model_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        issue_number=issue_number,
        task=task,
        agent_response=agent_response,
        has_changes=has_changes,
        branch_name=branch_name,
        input_tokens=token_stats.input_tokens,
        output_tokens=token_stats.output_tokens,
        llm_calls=token_stats.llm_calls,
        tool_calls=token_stats.tool_calls,
        estimated_cost=token_stats.estimated_cost,
        start_time=_start_time,
    )

    # Finalize progress — replace progress comment with execution report
    progress.finalize(success=True, execution_report=execution_report)

    # Output results for the workflow
    # agent_response keeps the raw output for downstream JSON parsing
    # execution_report is the formatted markdown for issue comments
    outputs = {
        "has_changes": has_changes,
        "branch_name": branch_name if has_changes else "",
        "agent_response": execution_report[:60000],
        "agent_response_raw": agent_response[:60000],
    }

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_changes={'true' if has_changes else 'false'}\n")
            f.write(f"branch_name={branch_name}\n")
            f.write(
                f"agent_response<<AGENT_RESPONSE_EOF_7f3c9a\n{execution_report[:60000]}\nAGENT_RESPONSE_EOF_7f3c9a\n"
            )
    else:
        print(json.dumps(outputs, indent=2))

    # Write GitHub Actions step summary (same report)
    write_step_summary(execution_report)

    return outputs


def main():
    task = os.environ.get("TASK", "")
    repo_dir = os.environ.get("REPO_DIR", os.getcwd())
    repo_owner = os.environ.get("REPO_OWNER", "")
    repo_name = os.environ.get("REPO_NAME", "")
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))

    if not task:
        logger.error("TASK environment variable is required")
        sys.exit(1)
    if not repo_owner or not repo_name:
        logger.error("REPO_OWNER and REPO_NAME are required")
        sys.exit(1)

    asyncio.run(run_agent(task, repo_dir, repo_owner, repo_name, issue_number))


if __name__ == "__main__":
    main()
