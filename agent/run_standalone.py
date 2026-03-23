"""Standalone agent runner for GitHub Actions.

Runs the Open SWE agent without LangGraph server — direct Deep Agent invocation.
Uses the GitHub Actions runner as the sandbox (SANDBOX_TYPE=local).
"""

import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("run_standalone")


async def run_agent(task: str, repo_dir: str, repo_owner: str, repo_name: str, issue_number: int):
    """Run the SWE agent on a task, then commit + open PR + comment."""
    from deepagents import create_deep_agent
    from deepagents.backends import LocalShellBackend

    from agent.aap_config import (
        get_agent_instruction,
        get_model_id,
        get_model_max_tokens,
        get_model_temperature,
        get_skill_instruction,
    )
    from agent.utils.model import make_model

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        logger.error("GITHUB_TOKEN not set")
        sys.exit(1)

    # Create local sandbox pointing at the cloned repo
    sandbox = LocalShellBackend(root_dir=repo_dir, inherit_env=True)

    # Configure git identity
    sandbox.execute("git config user.name 'aap-open-swe[bot]'")
    sandbox.execute("git config user.email 'aap-open-swe@users.noreply.github.com'")

    # Load model from manifest
    model_id = get_model_id()
    model = make_model(
        model_id,
        temperature=get_model_temperature(),
        max_tokens=get_model_max_tokens(),
    )

    # Check for skill-specific execution
    skill_id = os.environ.get("SKILL_ID", "")
    pr_number = int(os.environ.get("PR_NUMBER", "0"))

    # Build system prompt — skill overrides base if specified
    if skill_id and skill_id not in ("swe-coder", ""):
        skill_instruction = get_skill_instruction(skill_id)
        if skill_instruction:
            system_prompt = skill_instruction.format(
                working_dir=repo_dir,
                repo_owner=repo_owner,
                repo_name=repo_name,
                pr_number=pr_number,
                issue_number=issue_number,
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

    logger.info("Creating agent with model=%s", model_id)

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=[],
        backend=sandbox,
    )

    logger.info("Sending task to agent: %s", task[:200])

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": task}]},
    )

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

    logger.info("Agent finished with %d messages", len(messages))

    # Post review if skill is review-type
    if skill_id in ("code-review", "security-scan") and pr_number:
        from agent.review_poster import parse_review_output, post_pr_review

        review = parse_review_output(agent_response)
        if review:
            post_pr_review(repo_owner, repo_name, pr_number, review, skill_id)
        else:
            logger.warning("Could not parse structured review from agent output")

    # Check if agent made changes
    diff_result = sandbox.execute("git diff --stat HEAD")
    staged_result = sandbox.execute("git diff --cached --stat")
    status_result = sandbox.execute("git status --porcelain")

    has_changes = bool(
        (diff_result.output and diff_result.output.strip())
        or (staged_result.output and staged_result.output.strip())
        or (status_result.output and status_result.output.strip())
    )

    branch_name = f"aap-open-swe/issue-{issue_number}"

    if has_changes:
        if status_result.output and status_result.output.strip():
            # Uncommitted changes — commit them
            sandbox.execute("git add -A")
            sandbox.execute(f'git commit -m "fix: address issue #{issue_number}"')

        # Create branch and push
        sandbox.execute(f"git checkout -b {branch_name} 2>/dev/null || git checkout {branch_name}")
        push_result = sandbox.execute(
            f"git push https://x-access-token:{github_token}@github.com/{repo_owner}/{repo_name}.git {branch_name} --force"
        )

        if push_result.exit_code != 0:
            logger.error("Push failed: %s", push_result.output)
            has_changes = False

    # Output results for the workflow
    outputs = {
        "has_changes": has_changes,
        "branch_name": branch_name if has_changes else "",
        "agent_response": agent_response[:60000],  # GitHub has limits
    }

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_changes={'true' if has_changes else 'false'}\n")
            f.write(f"branch_name={branch_name}\n")
            # Multi-line output
            f.write(f"agent_response<<AGENT_EOF\n{agent_response[:60000]}\nAGENT_EOF\n")
    else:
        print(json.dumps(outputs, indent=2))

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
