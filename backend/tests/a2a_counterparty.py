"""Standalone runner for the scripted A2A counterparty (spec §19.7, §14d).

The acceptance campaign runs the SAME stub the contract tests use, as a
host process beside the smtp/webhook sinks — no new compose service. The
backend container reaches it over the docker bridge, so the card must
ADVERTISE the bridge IP while uvicorn binds a routable interface:

    .venv/bin/python -m tests.a2a_counterparty --port 8027 \
        --bind-host 0.0.0.0 --advertise-host 172.18.0.1 --auth apikey-header

Auth modes mirror StubA2AServer.auth (default: open). ``--extra-skill``
adds a third card skill live at any time via the control endpoint::

    curl -X POST http://127.0.0.1:8027/_control/add-skill

(card_modifier serves the mutated card on the next fetch — the §14d-40
card-drift step). The control route is loopback-convenience only and is
part of the test asset, never the product.
"""

import argparse
import asyncio

from a2a.types import AgentSkill
from starlette.requests import Request
from starlette.responses import JSONResponse

from tests.stub_a2a_server import StubA2AServer


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8027)
    parser.add_argument("--bind-host", default="0.0.0.0")  # noqa: S104 - sandbox test process
    parser.add_argument("--advertise-host", default="172.18.0.1")
    parser.add_argument("--auth", default=None, help="StubA2AServer auth mode (default open)")
    parser.add_argument("--name", default="stub-agent")
    args = parser.parse_args()

    stub = StubA2AServer(
        name=args.name,
        auth=args.auth,
        bind_host=args.bind_host,
        advertise_host=args.advertise_host,
        fixed_port=args.port,
    )
    await stub.start()

    async def add_skill(_request: Request) -> JSONResponse:
        skill = AgentSkill(
            id="translate",
            name="translate",
            description="Translate text between languages",
            tags=["text", "i18n"],
        )
        if all(s.id != skill.id for s in stub.skills):
            stub.skills.append(skill)
        return JSONResponse({"skills": [s.id for s in stub.skills]})

    assert stub._server is not None  # noqa: S101, SLF001 - test asset introspects its own stub
    from typing import Any, cast

    from starlette.routing import Route

    gate = cast(Any, stub._server.config.app)  # noqa: SLF001 - the _AuthGate wrapper
    gate.inner.router.routes.append(Route("/_control/add-skill", add_skill, methods=["POST"]))

    print(  # noqa: T201 - runner status line
        f"a2a counterparty '{args.name}' auth={args.auth or 'open'} "
        f"card={stub.card_url} (bound {args.bind_host}:{stub.port})",
        flush=True,
    )
    try:
        await asyncio.Event().wait()  # serve until killed
    finally:
        await stub.stop()


if __name__ == "__main__":
    asyncio.run(_main())
