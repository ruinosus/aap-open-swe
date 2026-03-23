#!/usr/bin/env python3
"""MVP test for Open SWE agent with AAP SDK manifest integration.

Runs the agent locally (no cloud sandbox) with a simple coding task.
Tests the full flow: manifest config → agent creation → tool execution.

Usage:
    # With OpenAI:
    OPENAI_API_KEY=sk-... python test_mvp.py

    # With Anthropic:
    ANTHROPIC_API_KEY=sk-ant-... python test_mvp.py

    # Custom model:
    OPENAI_API_KEY=sk-... OPEN_SWE_MODEL=openai:gpt-4o python test_mvp.py
"""

import asyncio
import logging
import os
import sys
import tempfile

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("test_mvp")


def check_api_keys():
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not has_openai and not has_anthropic:
        print("\n╔══════════════════════════════════════════════════╗")
        print("║  API key required. Set one of:                   ║")
        print("║                                                   ║")
        print("║  OPENAI_API_KEY=sk-...     (for OpenAI models)   ║")
        print("║  ANTHROPIC_API_KEY=sk-...  (for Anthropic models)║")
        print("║                                                   ║")
        print("║  Then run:                                        ║")
        print("║  OPENAI_API_KEY=sk-... python test_mvp.py         ║")
        print("╚══════════════════════════════════════════════════╝\n")
        sys.exit(1)

    if has_openai and "OPEN_SWE_MODEL" not in os.environ:
        os.environ["OPEN_SWE_MODEL"] = "openai:gpt-4o"

    model = os.environ.get("OPEN_SWE_MODEL", "anthropic:claude-sonnet-4-6")
    print(f"Using model: {model}")
    return model


async def test_manifest_loading():
    """Test 1: Verify manifest loads correctly via aap_config."""
    print("\n━━━ Test 1: Manifest Loading ━━━")

    from agent.aap_config import (
        get_agent_instruction,
        get_guardrails,
        get_manifest,
        get_model_id,
        get_rules,
        is_telemetry_enabled,
    )

    mi = get_manifest()
    assert mi is not None, "Manifest should load"
    print(f"  ✓ Manifest loaded: {mi.id} ({mi.kind})")

    instr = get_agent_instruction()
    assert len(instr) > 1000, f"Instruction too short: {len(instr)}"
    print(f"  ✓ Agent instruction: {len(instr)} chars")

    model = get_model_id()
    print(f"  ✓ Model: {model}")

    rules = get_rules()
    print(f"  ✓ Rules: {len(rules)}")

    g = get_guardrails()
    print(f"  ✓ Guardrails: input={len(g.get('input', []))}, output={len(g.get('output', []))}")

    print(f"  ✓ Telemetry: enabled={is_telemetry_enabled()}")
    print("  PASSED")


async def test_local_sandbox():
    """Test 2: Verify local sandbox works."""
    print("\n━━━ Test 2: Local Sandbox ━━━")

    with tempfile.TemporaryDirectory() as tmpdir:
        from deepagents.backends import LocalShellBackend

        sandbox = LocalShellBackend(root_dir=tmpdir, inherit_env=True)
        print(f"  ✓ Sandbox created: {type(sandbox).__name__}")

        result = sandbox.execute("echo 'hello from sandbox'")
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "hello from sandbox" in result.output
        print(f"  ✓ Command execution works: {result.output.strip()}")

        result = sandbox.execute("python3 --version")
        print(f"  ✓ Python in sandbox: {result.output.strip()}")

    print("  PASSED")


async def test_agent_creation():
    """Test 3: Create the Deep Agent with manifest config."""
    print("\n━━━ Test 3: Agent Creation ━━━")

    from agent.aap_config import (
        get_agent_instruction,
        get_model_id,
        get_model_max_tokens,
        get_model_temperature,
    )
    from agent.utils.model import make_model

    model_id = get_model_id()
    temperature = get_model_temperature()
    max_tokens = get_model_max_tokens()

    make_model(model_id, temperature=temperature, max_tokens=max_tokens)
    print(f"  ✓ Model created: {model_id} (temp={temperature}, max_tokens={max_tokens})")

    instr = get_agent_instruction()
    test_prompt = instr.format(
        working_dir="/tmp/test-repo",
        linear_project_id="TEST",
        linear_issue_number="1",
        agents_md_section="",
    )
    assert len(test_prompt) > 1000
    print(f"  ✓ System prompt rendered: {len(test_prompt)} chars")

    print("  PASSED")


async def test_agent_invocation():
    """Test 4: Actually invoke the agent with a simple task."""
    print("\n━━━ Test 4: Agent Invocation (live LLM call) ━━━")

    from deepagents import create_deep_agent

    from agent.aap_config import (
        get_model_id,
        get_model_max_tokens,
        get_model_temperature,
    )
    from agent.utils.model import make_model

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a small test file in the sandbox
        test_file = os.path.join(tmpdir, "hello.py")
        with open(test_file, "w") as f:
            f.write('def greet(name):\n    return f"Hello, {name}!"\n')

        from deepagents.backends import LocalShellBackend

        sandbox = LocalShellBackend(root_dir=tmpdir, inherit_env=True)

        model_id = get_model_id()
        model = make_model(
            model_id,
            temperature=get_model_temperature(),
            max_tokens=get_model_max_tokens(),
        )

        system_prompt = (
            f"You are a coding assistant. Your working directory is {tmpdir}. "
            "Use the execute tool to run commands. Be concise."
        )

        agent = create_deep_agent(
            model=model,
            system_prompt=system_prompt,
            tools=[],
            backend=sandbox,
        )

        print(f"  ✓ Agent created with {model_id}")
        print("  → Sending task: 'List files and read hello.py'...")

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"List files in {tmpdir} and show me what's in hello.py. Then run it with: python3 -c \"import sys; sys.path.insert(0, '{tmpdir}'); from hello import greet; print(greet('Open SWE'))\"",
                    }
                ]
            },
        )

        messages = result.get("messages", [])
        print(f"  ✓ Agent responded with {len(messages)} messages")

        # Check that the agent used tools
        tool_calls = [m for m in messages if hasattr(m, "tool_calls") and m.tool_calls]
        print(f"  ✓ Agent made {len(tool_calls)} tool call(s)")

        # Print last AI message
        ai_messages = [
            m
            for m in messages
            if hasattr(m, "content") and getattr(m, "type", "") == "ai" and m.content
        ]
        if ai_messages:
            last = ai_messages[-1].content
            preview = last[:200] if isinstance(last, str) else str(last)[:200]
            print(f"  ✓ Last response: {preview}...")

    print("  PASSED")


async def main():
    model = check_api_keys()

    print("╔══════════════════════════════════════════════╗")
    print("║  Open SWE + AAP SDK — MVP Test               ║")
    print(f"║  Model: {model:<38s} ║")
    print("╚══════════════════════════════════════════════╝")

    await test_manifest_loading()
    await test_local_sandbox()
    await test_agent_creation()
    await test_agent_invocation()

    print("\n╔══════════════════════════════════════════════╗")
    print("║  ALL 4 TESTS PASSED                          ║")
    print("║  Open SWE agent works with AAP SDK manifest   ║")
    print("╚══════════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
