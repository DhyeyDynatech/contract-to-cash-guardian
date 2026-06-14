"""
aiohttp server glue for the Microsoft 365 Agents SDK (custom engine agent).
Hosts the bot's /api/messages endpoint that Azure Bot Service (and therefore
Microsoft 365 Copilot) calls. Adapted from the official Agents SDK quickstart.
"""
from os import environ

from aiohttp.web import Application, Request, Response, run_app
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import AgentApplication, AgentAuthConfiguration


def start_server(
    agent_application: AgentApplication,
    auth_configuration: AgentAuthConfiguration | None,
):
    async def entry_point(req: Request) -> Response:
        agent: AgentApplication = req.app["agent_app"]
        adapter: CloudAdapter = req.app["adapter"]
        return await start_agent_process(req, agent, adapter)

    APP = Application(middlewares=[jwt_authorization_middleware])
    APP.router.add_post("/api/messages", entry_point)
    APP.router.add_get("/api/messages", lambda _: Response(status=200))
    APP["agent_configuration"] = auth_configuration
    APP["agent_app"] = agent_application
    APP["adapter"] = agent_application.adapter

    # HOST=0.0.0.0 when deploying (Azure App Service); localhost is fine locally.
    host = environ.get("HOST", "localhost")
    port = int(environ.get("PORT", 3978))
    run_app(APP, host=host, port=port)
