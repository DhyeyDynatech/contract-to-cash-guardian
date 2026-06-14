"""
Contract-to-Cash Guardian - Custom Engine Agent (bot endpoint)
---------------------------------------------------------------
The bot that surfaces in Microsoft 365 Copilot Chat. It receives messages on
/api/messages (via Azure Bot Service) and routes each turn to the Claude-powered
agent core, which calls the deterministic reconciler for real, cited findings.

Auth is built from environment variables (the CONNECTIONS__SERVICE_CONNECTION__*
keys) via the Agents SDK MSAL connection manager:
  - Local / Agents Playground: SERVICE_CONNECTION SETTINGS ANONYMOUS_ALLOWED=true
  - Connected (Copilot):        SETTINGS AUTHTYPE=ClientSecret + CLIENTID/CLIENTSECRET/TENANTID

Run locally:   python src/bot.py      (listens on localhost:3978)
Deploy:        provisioned as an Azure Bot; see m365agents.yml + infra/.
"""
from __future__ import annotations

import asyncio
import sys
from os import environ
from pathlib import Path

from dotenv import load_dotenv

# Load env from the project root BEFORE building SDK config from env vars.
# .env          = local/anonymous defaults (Agents Playground)
# .localConfigs = connected client-secret auth for Copilot, written by the
#                 Agents Toolkit deploy step; it overrides .env when present.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".localConfigs", override=True)

from microsoft_agents.activity import load_configuration_from_env  # noqa: E402
from microsoft_agents.authentication.msal import MsalConnectionManager  # noqa: E402
from microsoft_agents.hosting.aiohttp import CloudAdapter  # noqa: E402
from microsoft_agents.hosting.core import (  # noqa: E402
    AgentApplication,
    Authorization,
    MemoryStorage,
    TurnContext,
    TurnState,
)

from agent_core import run_agent  # noqa: E402
from start_server import start_server  # noqa: E402

# Build SDK config + auth from environment (CONNECTIONS__* keys).
agents_sdk_config = load_configuration_from_env(environ)

STORAGE = MemoryStorage()
CONNECTION_MANAGER = MsalConnectionManager(**agents_sdk_config)
ADAPTER = CloudAdapter(connection_manager=CONNECTION_MANAGER)
AUTHORIZATION = Authorization(STORAGE, CONNECTION_MANAGER, **agents_sdk_config)

AGENT_APP = AgentApplication[TurnState](
    storage=STORAGE,
    adapter=ADAPTER,
    authorization=AUTHORIZATION,
    **agents_sdk_config,
)

# Per-conversation Claude message history (in-process; fine for a single-instance demo).
_HISTORY: dict[str, list] = {}

WELCOME = (
    "👋 I'm the **Contract-to-Cash Guardian**. I find revenue leakage between what "
    "your contracts promised, what was billed, and what was delivered — with the "
    "exact cited rule and a human-approved fix.\n\n"
    "Try: *“Find revenue leakage across the contract portfolio.”*"
)


@AGENT_APP.conversation_update("membersAdded")
async def _on_members_added(context: TurnContext, _: TurnState):
    # Greet exactly once: only when a real (non-bot) member is added.
    bot_id = context.activity.recipient.id if context.activity.recipient else None
    added = context.activity.members_added or []
    if any(getattr(m, "id", None) != bot_id for m in added):
        await context.send_activity(WELCOME)
    return True


@AGENT_APP.message("/help")
async def _on_help(context: TurnContext, _: TurnState):
    await context.send_activity(WELCOME)
    return True


@AGENT_APP.activity("message")
async def on_message(context: TurnContext, _: TurnState):
    user_text = (context.activity.text or "").strip()
    if not user_text:
        return True

    # Show a typing indicator — the multi-IQ tool chain can take 20-40s, and
    # without this Teams renders an empty placeholder bubble before the answer.
    try:
        from microsoft_agents.activity import Activity, ActivityTypes

        await context.send_activity(Activity(type=ActivityTypes.typing))
    except Exception:  # noqa: BLE001 - typing is best-effort
        pass

    convo_id = context.activity.conversation.id
    history = _HISTORY.get(convo_id, [])

    try:
        # run_agent makes blocking Anthropic calls — run off the event loop.
        reply, updated = await asyncio.to_thread(run_agent, user_text, history)
        _HISTORY[convo_id] = updated
    except Exception as error:  # noqa: BLE001 - surface a friendly message
        reply = f"Sorry — I hit an error reaching the model: {error}"

    await context.send_activity(reply)
    return True


@AGENT_APP.error
async def on_error(context: TurnContext, error: Exception):
    import traceback

    print(f"[on_error] {error}", file=sys.stderr)
    traceback.print_exc()
    await context.send_activity(
        "Something went wrong handling that. Please try again."
    )


if __name__ == "__main__":
    start_server(
        agent_application=AGENT_APP,
        auth_configuration=CONNECTION_MANAGER.get_default_connection_configuration(),
    )
