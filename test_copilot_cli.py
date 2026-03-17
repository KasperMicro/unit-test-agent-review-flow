"""Quick test to verify Copilot CLI connectivity with BYOK."""
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from copilot import CopilotClient
from copilot.types import PermissionRequestResult
from agents.copilot_sdk_agent import _build_byok_provider


def auto_approve(request, context):
    """Auto-approve everything for testing."""
    kind = request.get("kind", "unknown")
    print(f"  [PERMISSION] kind={kind}", flush=True)
    return PermissionRequestResult(kind="approved")


def handle_event(event):
    """Log all session events."""
    etype = event.type
    data = event.data
    print(f"  [EVENT] {etype}", flush=True)
    if data:
        if hasattr(data, 'content') and data.content:
            print(f"    content: {str(data.content)[:300]}", flush=True)
        if hasattr(data, 'message') and data.message:
            print(f"    message: {str(data.message)[:300]}", flush=True)
        if hasattr(data, 'tool_name') and data.tool_name:
            print(f"    tool: {data.tool_name}", flush=True)


async def test():
    client = CopilotClient({"log_level": "info"})
    try:
        await client.start()
        print("CLI started successfully", flush=True)

        workspace = os.path.abspath("./cloned_code")
        provider = _build_byok_provider()
        print(f"BYOK provider: {provider['type']} -> {provider['base_url']}", flush=True)

        config = {
            "streaming": False,
            "working_directory": workspace,
            "on_permission_request": auto_approve,
            "provider": provider,
        }
        session = await client.create_session(config)
        print("Session created", flush=True)

        session.on(handle_event)

        result = await session.send_and_wait(
            {"prompt": "Say hello in one word."},
            timeout=30,
        )
        if result and result.data and result.data.content:
            print(f"Response: {result.data.content[:500]}", flush=True)
        else:
            print(f"Result: {result}", flush=True)

        print("Done!", flush=True)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", flush=True)
    finally:
        await client.stop()


asyncio.run(test())
