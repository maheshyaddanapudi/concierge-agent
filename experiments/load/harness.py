#!/usr/bin/env python
"""Load harness — drives the SHIPPED API of a running stack (M49).

Nothing here reaches into the process: every number comes from the HTTP
surface a user would hit, plus `pg_stat_activity` for the connection budget.
The fake provider (`FAKE_LLM_ENABLED=1` on the backend, spec §11) makes runs
deterministic and key-free so the numbers measure the SYSTEM, not a model;
`--model openrouter:qwen/qwen3.8-max` points the same scenarios at a live
model for an end-to-end sample.

Scenarios (pick with --scenarios, default all):

  api         read-path latency at rest: /runs, /conversations, /skills,
              /tools, /settings, /memories/recall — p50/p95 under concurrency
  runs-scale  /runs and /conversations latency as the run table grows
              (seeded via SQL at each --runs-sizes step; the 10× growth test)
  chat        N concurrent POST /chat runs to terminal state, per
              --chat-concurrency level — submit and end-to-end latency
  sse         concurrent /chat/stream subscribers on a run paused at a HITL
              gate, opened in steps with a probe request after each step:
              the first step whose probe fails is the SSE ceiling; then the
              global /ambient/stream, which holds no DB session, as contrast
  recall      /memories/recall latency at seeded corpus sizes
              (--recall-sizes, fake 64-dim embeddings under the fake key)
  ambient     webhook backlog: N routine fires, time-to-drain and the
              fired/held split, runs to terminal state

Every seeded row carries the `loadgen` marker and is removed at the end
unless --keep-data; settings the harness touches are restored.

Usage (from the repo root, backend venv):
    cd backend && .venv/bin/python ../experiments/load/harness.py \
        --out ../docs/acceptance/prod/M49/baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

API = "/api/v1"
LOADGEN = "loadgen"
FAKE_MODEL = "fake:scripted"
FAKE_EMBED_KEY = "fake:scripted@64"
TERMINAL = {"completed", "failed", "cancelled", "stalled"}
TOUCHED_SETTINGS = (
    "default_model",
    "embedding_model",
    "memory_enabled",
    "ambient_enabled",
    "ambient_routine_events_per_hour",
    "ambient_runs_per_day",
)


def log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return round(s[int(k)], 2)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def summarize(ms: list[float]) -> dict[str, Any]:
    if not ms:
        return {"n": 0}
    return {
        "n": len(ms),
        "p50_ms": pct(ms, 0.5),
        "p95_ms": pct(ms, 0.95),
        "p99_ms": pct(ms, 0.99),
        "max_ms": round(max(ms), 2),
        "mean_ms": round(statistics.fmean(ms), 2),
    }


async def pg_activity(conn: asyncpg.Connection) -> dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT coalesce(state, 'none') AS state, count(*) AS n
        FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
          AND application_name NOT LIKE 'loadgen%'
        GROUP BY state
        """
    )
    out = {"total": 0}
    for r in rows:
        out[str(r["state"]).replace(" ", "_")] = int(r["n"])
        out["total"] += int(r["n"])
    return out


class Sampler:
    """Background pg_stat_activity sampler: the connection PEAK per scenario."""

    def __init__(self, pool: asyncpg.Pool, interval: float = 0.2) -> None:
        self.pool = pool
        self.interval = interval
        self.peak_total = 0
        self.peak_active = 0
        self.samples = 0
        self._task: asyncio.Task[None] | None = None

    async def _loop(self) -> None:
        while True:
            try:
                async with self.pool.acquire() as conn:
                    snap = await pg_activity(conn)
                self.peak_total = max(self.peak_total, snap["total"])
                self.peak_active = max(self.peak_active, snap.get("active", 0))
                self.samples += 1
            except Exception as exc:  # noqa: BLE001 — a sampler hiccup is not a result
                log(f"sampler: {exc}")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> dict[str, int]:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        return {
            "peak_connections": self.peak_total,
            "peak_active": self.peak_active,
            "samples": self.samples,
        }


class Harness:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.http = httpx.AsyncClient(
            base_url=args.base_url,
            timeout=httpx.Timeout(30.0, read=90.0),
            limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
        )
        self.probe = httpx.AsyncClient(base_url=args.base_url, timeout=args.probe_timeout)
        self.pg: asyncpg.Pool | None = None
        self.results: dict[str, Any] = {}
        self.settings_before: dict[str, Any] = {}

    # ── lifecycle ──────────────────────────────────────────────────

    async def open(self) -> None:
        self.pg = await asyncpg.create_pool(
            self.args.database_url,
            min_size=1,
            max_size=4,
            server_settings={"application_name": "loadgen-harness"},
        )
        settings = await self.get_settings()
        self.settings_before = {k: settings.get(k) for k in TOUCHED_SETTINGS}

    async def close(self) -> None:
        await self.http.aclose()
        await self.probe.aclose()
        if self.pg:
            await self.pg.close()

    async def restore_settings(self) -> None:
        current = await self.get_settings()
        changes = {
            k: v for k, v in self.settings_before.items() if current.get(k) != v
        }
        if changes:
            log(f"restoring settings: {sorted(changes)}")
            await self.patch_settings(**changes)

    # ── api helpers ────────────────────────────────────────────────

    async def get_settings(self) -> dict[str, Any]:
        resp = await self.http.get(f"{API}/settings")
        resp.raise_for_status()
        return dict(resp.json())

    async def patch_settings(self, **kv: Any) -> dict[str, Any]:
        resp = await self.http.patch(f"{API}/settings", json=kv)
        if resp.status_code != 200:
            raise RuntimeError(f"PATCH settings {kv} -> {resp.status_code} {resp.text[:300]}")
        return dict(resp.json())

    async def timed_get(self, client: httpx.AsyncClient, path: str) -> tuple[float, int, int]:
        t0 = time.perf_counter()
        try:
            resp = await client.get(path)
            return (time.perf_counter() - t0) * 1000, resp.status_code, len(resp.content)
        except httpx.HTTPError as exc:
            return (time.perf_counter() - t0) * 1000, -1, len(str(exc))

    async def bounded(self, coros: list[Any], concurrency: int) -> list[Any]:
        sem = asyncio.Semaphore(concurrency)

        async def run(c: Any) -> Any:
            async with sem:
                return await c

        return await asyncio.gather(*(run(c) for c in coros))

    async def sql(self, query: str, *params: Any) -> Any:
        assert self.pg is not None
        async with self.pg.acquire() as conn:
            return await conn.fetch(query, *params)

    async def sql_val(self, query: str, *params: Any) -> Any:
        assert self.pg is not None
        async with self.pg.acquire() as conn:
            return await conn.fetchval(query, *params)

    async def sql_exec(self, query: str, *params: Any) -> str:
        assert self.pg is not None
        async with self.pg.acquire() as conn:
            return str(await conn.execute(query, *params))

    async def at_rest(self) -> dict[str, Any]:
        assert self.pg is not None
        async with self.pg.acquire() as conn:
            act = await pg_activity(conn)
            max_conn = await conn.fetchval("SHOW max_connections")
        return {"connections": act, "max_connections": int(max_conn)}

    async def wait_run(self, run_id: str, deadline_s: float) -> dict[str, Any]:
        t0 = time.perf_counter()
        last: dict[str, Any] = {}
        while time.perf_counter() - t0 < deadline_s:
            resp = await self.http.get(f"{API}/runs/{run_id}")
            if resp.status_code == 200:
                last = resp.json()
                if last.get("status") in TERMINAL or last.get("status") == "paused_hitl":
                    return last
            await asyncio.sleep(0.25)
        return {**last, "status": last.get("status", "unknown"), "timed_out": True}

    # ── scenarios ──────────────────────────────────────────────────

    async def scenario_api(self) -> dict[str, Any]:
        n, conc = self.args.api_requests, self.args.api_concurrency
        endpoints = {
            "GET /runs": f"{API}/runs",
            "GET /conversations": f"{API}/conversations",
            "GET /skills": f"{API}/skills",
            "GET /tools": f"{API}/tools",
            "GET /settings": f"{API}/settings",
            "GET /memories/recall": f"{API}/memories/recall?q=aurora+deploy+latency&k=6",
        }
        out: dict[str, Any] = {"requests_per_endpoint": n, "concurrency": conc, "endpoints": {}}
        assert self.pg is not None
        sampler = Sampler(self.pg)
        sampler.start()
        for name, path in endpoints.items():
            rows = await self.bounded([self.timed_get(self.http, path) for _ in range(n)], conc)
            ok = [ms for ms, code, _ in rows if code == 200]
            errors: dict[str, int] = {}
            for _, code, _ in rows:
                if code != 200:
                    errors[str(code)] = errors.get(str(code), 0) + 1
            out["endpoints"][name] = {
                **summarize(ok),
                "errors": errors,
                "bytes": rows[0][2] if rows else 0,
            }
            log(f"api {name}: p50 {out['endpoints'][name].get('p50_ms')} ms, errors {errors}")
        out["connections"] = await sampler.stop()
        return out

    async def _seed_runs(self, target: int) -> int:
        """Bring the loadgen run count up to `target` (delta insert)."""
        have = int(await self.sql_val("SELECT count(*) FROM runs WHERE chat_message LIKE $1", f"{LOADGEN} question %"))
        if have >= target:
            return have
        convs = int(await self.sql_val("SELECT count(*) FROM conversations WHERE title LIKE $1", f"{LOADGEN} conversation %"))
        if convs < 100:
            await self.sql_exec(
                """
                INSERT INTO conversations (id, title)
                SELECT gen_random_uuid(), $1 || ' conversation ' || g
                FROM generate_series($2::int, 100) g
                """,
                LOADGEN,
                convs + 1,
            )
        delta = target - have
        await self.sql_exec(
            """
            WITH cids AS (
              SELECT array_agg(id ORDER BY title) AS a FROM conversations WHERE title LIKE $1 || ' conversation %'
            )
            INSERT INTO runs (id, conversation_id, chat_message, status, orchestrator_mode,
                              include_history_summary, include_memories, is_eval, final_answer,
                              started_at, finished_at, total_input_tokens, total_output_tokens)
            SELECT gen_random_uuid(), (cids.a)[1 + (g % array_length(cids.a, 1))],
                   $1 || ' question ' || g, 'completed', 'graph', false, false, false,
                   $1 || ' answer ' || g || ' ' || repeat('x', 400),
                   now() - (g || ' seconds')::interval, now(), 100, 20
            FROM cids, generate_series($2::int, $3::int) g
            """,
            LOADGEN,
            have + 1,
            target,
        )
        await self.sql_exec(
            """
            INSERT INTO run_steps (id, run_id, step_type, status, input_tokens, output_tokens,
                                   started_at, finished_at, model, node_id, output)
            SELECT gen_random_uuid(), r.id, s.t, 'completed', 50, 10, r.started_at, r.finished_at,
                   'fake:scripted', s.t, '{"answer": "loadgen"}'::jsonb
            FROM runs r, (VALUES ('plan'), ('aggregate'), ('skill')) AS s(t)
            WHERE r.chat_message LIKE $1 || ' question %'
              AND NOT EXISTS (SELECT 1 FROM run_steps rs WHERE rs.run_id = r.id)
            """,
            LOADGEN,
        )
        await self.sql_exec("ANALYZE runs; ANALYZE run_steps; ANALYZE conversations")
        return int(await self.sql_val("SELECT count(*) FROM runs WHERE chat_message LIKE $1", f"{LOADGEN} question %"))

    async def scenario_runs_scale(self) -> dict[str, Any]:
        out: dict[str, Any] = {"levels": []}
        n = self.args.runs_requests
        for size in self.args.runs_sizes:
            seeded = await self._seed_runs(size)
            total_runs = int(await self.sql_val("SELECT count(*) FROM runs"))
            level: dict[str, Any] = {"loadgen_runs": seeded, "total_runs": total_runs}
            for name, path in (("GET /runs", f"{API}/runs"), ("GET /conversations", f"{API}/conversations")):
                rows = await self.bounded([self.timed_get(self.http, path) for _ in range(n)], 1)
                ok = [ms for ms, code, _ in rows if code == 200]
                level[name] = {**summarize(ok), "bytes": rows[-1][2] if rows else 0,
                               "errors": sum(1 for _, code, _ in rows if code != 200)}
                log(f"runs-scale {total_runs} runs {name}: p50 {level[name].get('p50_ms')} ms, {level[name]['bytes']} bytes")
            out["levels"].append(level)
        return out

    async def _chat_level(self, concurrency: int) -> dict[str, Any]:
        deadline = self.args.chat_deadline
        assert self.pg is not None
        sampler = Sampler(self.pg)
        sampler.start()
        t_start = time.perf_counter()

        async def one(i: int) -> dict[str, Any]:
            t0 = time.perf_counter()
            try:
                resp = await self.http.post(
                    f"{API}/chat", json={"message": f"{LOADGEN} chat {uuid.uuid4().hex[:8]} #{i}: say hello"}
                )
            except httpx.HTTPError as exc:
                return {"submit_ms": (time.perf_counter() - t0) * 1000, "status": "submit_error", "error": str(exc)[:200]}
            submit_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code != 201:
                return {"submit_ms": submit_ms, "status": f"http_{resp.status_code}", "error": resp.text[:200]}
            run_id = resp.json()["run_id"]
            final = await self.wait_run(run_id, deadline)
            return {
                "submit_ms": submit_ms,
                "e2e_ms": (time.perf_counter() - t0) * 1000,
                "status": final.get("status"),
                "error": (final.get("error") or "")[:200] or None,
                "timed_out": bool(final.get("timed_out")),
            }

        rows = await asyncio.gather(*(one(i) for i in range(concurrency)))
        wall = time.perf_counter() - t_start
        statuses: dict[str, int] = {}
        for r in rows:
            statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1
        errors = sorted({r["error"] for r in rows if r.get("error")})[:5]
        completed = [r["e2e_ms"] for r in rows if r.get("status") == "completed"]
        return {
            "concurrency": concurrency,
            "wall_s": round(wall, 2),
            "statuses": statuses,
            "submit": summarize([r["submit_ms"] for r in rows]),
            "end_to_end_completed": summarize(completed),
            "throughput_runs_per_s": round(len(completed) / wall, 2) if wall else None,
            "sample_errors": errors,
            "connections": await sampler.stop(),
        }

    async def scenario_chat(self) -> dict[str, Any]:
        await self.patch_settings(default_model=self.args.model)
        out: dict[str, Any] = {"model": self.args.model, "levels": []}
        for c in self.args.chat_concurrency:
            log(f"chat: {c} concurrent runs on {self.args.model}")
            level = await self._chat_level(c)
            log(f"chat {c}: statuses {level['statuses']} e2e p95 {level['end_to_end_completed'].get('p95_ms')} ms "
                f"peak conns {level['connections']['peak_connections']}")
            out["levels"].append(level)
            await asyncio.sleep(2)
        return out

    async def _open_stream(self, path: str) -> tuple[httpx.Response, Any] | None:
        req = self.http.build_request("GET", path)
        try:
            resp = await self.http.send(req, stream=True)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            await resp.aclose()
            return None
        it = resp.aiter_lines()
        try:
            await asyncio.wait_for(it.__anext__(), timeout=15)
        except (StopAsyncIteration, TimeoutError, httpx.HTTPError):
            await resp.aclose()
            return None
        return resp, it

    async def _probe(self) -> dict[str, Any]:
        rows = [await self.timed_get(self.probe, f"{API}/runs?routine_id={uuid.uuid4()}") for _ in range(3)]
        ok = [ms for ms, code, _ in rows if code == 200]
        return {"ok": len(ok), "failed": 3 - len(ok), "p50_ms": pct(ok, 0.5), "codes": [c for _, c, _ in rows]}

    async def _stream_ceiling(self, path: str, step: int, maximum: int) -> dict[str, Any]:
        streams: list[tuple[httpx.Response, Any]] = []
        levels: list[dict[str, Any]] = []
        first_failure: int | None = None
        assert self.pg is not None
        try:
            opened = 0
            while opened < maximum:
                batch = min(step, maximum - opened)
                results = await asyncio.gather(*(self._open_stream(path) for _ in range(batch)))
                got = [r for r in results if r is not None]
                streams.extend(got)
                opened += batch
                probe = await self._probe()
                async with self.pg.acquire() as conn:
                    act = await pg_activity(conn)
                levels.append({"streams_attempted": opened, "streams_open": len(streams), "probe": probe, "connections": act})
                log(f"sse {path}: {len(streams)} open, probe ok {probe['ok']}/3 p50 {probe['p50_ms']} ms, conns {act['total']}")
                if probe["failed"] and first_failure is None:
                    first_failure = opened
                    break
                if len(got) < batch and first_failure is None:
                    first_failure = opened
                    break
        finally:
            for resp, _ in streams:
                try:
                    await resp.aclose()
                except Exception:  # noqa: BLE001
                    pass
        # recovery: how long until the probe passes again after streams close
        t0 = time.perf_counter()
        recovered_ms: float | None = None
        while time.perf_counter() - t0 < 60:
            probe = await self._probe()
            if probe["ok"] == 3:
                recovered_ms = round((time.perf_counter() - t0) * 1000, 1)
                break
            await asyncio.sleep(0.5)
        ok_levels = [lv["streams_open"] for lv in levels if not lv["probe"]["failed"]]
        return {
            "path": path,
            "step": step,
            "max_attempted": maximum,
            "levels": levels,
            "max_streams_with_healthy_probe": max(ok_levels) if ok_levels else 0,
            "first_failure_at_streams": first_failure,
            "recovery_after_close_ms": recovered_ms,
        }

    async def scenario_sse(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        await self.patch_settings(default_model=self.args.model)
        resp = await self.http.get(f"{API}/sub-agents")
        resp.raise_for_status()
        agent = next((a for a in resp.json() if a["name"] == "research-concierge"), None)
        run_id: str | None = None
        if agent is None:
            out["chat_stream"] = {"error": "research-concierge not seeded"}
        else:
            resp = await self.http.post(
                f"{API}/chat",
                json={"message": f"{LOADGEN}: research pgvector index types", "target_sub_agent_id": agent["id"]},
            )
            if resp.status_code != 201:
                out["chat_stream"] = {"error": f"POST /chat -> {resp.status_code} {resp.text[:200]}"}
            else:
                run_id = resp.json()["run_id"]
                final = await self.wait_run(run_id, 90)
                out["paused_run"] = {"run_id": run_id, "status": final.get("status"), "error": final.get("error")}
                if final.get("status") == "paused_hitl":
                    out["chat_stream"] = await self._stream_ceiling(
                        f"{API}/chat/stream/{run_id}", self.args.sse_step, self.args.sse_max
                    )
                else:
                    out["chat_stream"] = {"error": f"run did not pause at the HITL gate: {final.get('status')}"}
        if run_id:
            await self.http.post(f"{API}/runs/{run_id}/cancel")
        # contrast: the global ambient stream holds no session
        await self.patch_settings(ambient_enabled=True)
        out["ambient_stream"] = await self._stream_ceiling(f"{API}/ambient/stream", self.args.sse_step * 4, self.args.sse_max * 2)
        return out

    async def _seed_memories(self, target: int) -> int:
        have = int(await self.sql_val("SELECT count(*) FROM memories WHERE text LIKE $1", f"{LOADGEN} memory %"))
        if have < target:
            await self.sql_exec(
                """
                INSERT INTO memories (id, scope, kind, text, importance, confidence, source, status,
                                      valid_from, recorded_at, last_accessed_at, access_count, pinned)
                SELECT gen_random_uuid(), 'global',
                       (ARRAY['fact','preference','entity','relation'])[1 + g % 4],
                       $1 || ' memory ' || g || ' about '
                         || (ARRAY['aurora','biscuit','lisbon','release','deploy','invoice','pgvector','latency'])[1 + g % 8]
                         || ' topic ' || (g % 977) || ' ' || md5(g::text),
                       1 + g % 10, 0.5 + (g % 50) / 100.0, 'user_stated', 'active',
                       now(), now() - (g || ' minutes')::interval, now() - (g || ' minutes')::interval, 0, false
                FROM generate_series($2::int, $3::int) g
                """,
                LOADGEN,
                have + 1,
                target,
            )
        await self.sql_exec(
            """
            INSERT INTO memory_embeddings (ref_id, table_ref, model_key, embedding)
            SELECT m.id, 'memories', $2::text,
                   (SELECT array_agg(random())::vector FROM generate_series(1, 64) WHERE m.id IS NOT NULL)
            FROM memories m
            WHERE m.text LIKE $1::text || ' memory %'
              AND NOT EXISTS (SELECT 1 FROM memory_embeddings e
                              WHERE e.ref_id = m.id AND e.table_ref = 'memories' AND e.model_key = $2::text)
            """,
            LOADGEN,
            FAKE_EMBED_KEY,
        )
        await self.sql_exec("ANALYZE memories; ANALYZE memory_embeddings")
        return int(await self.sql_val("SELECT count(*) FROM memories WHERE text LIKE $1", f"{LOADGEN} memory %"))

    async def scenario_recall(self) -> dict[str, Any]:
        await self.patch_settings(memory_enabled=True, embedding_model=FAKE_MODEL)
        queries = [
            "aurora deploy latency",
            "biscuit lisbon invoice",
            "pgvector release topic 123",
            "invoice for the deploy of aurora",
            "what is the latency of release",
        ]
        out: dict[str, Any] = {"embedding_key": FAKE_EMBED_KEY, "levels": []}
        n = self.args.recall_requests
        for size in self.args.recall_sizes:
            seeded = await self._seed_memories(size)
            total = int(await self.sql_val("SELECT count(*) FROM memories WHERE status = 'active'"))
            vectors = int(await self.sql_val("SELECT count(*) FROM memory_embeddings WHERE model_key = $1", FAKE_EMBED_KEY))
            for q in queries[:2]:  # warm
                await self.timed_get(self.http, f"{API}/memories/recall?q={q.replace(' ', '+')}&k=6")
            level: dict[str, Any] = {"loadgen_memories": seeded, "active_memories": total, "fake_vectors": vectors}
            for conc in (1, 5):
                rows = await self.bounded(
                    [self.timed_get(self.http, f"{API}/memories/recall?q={queries[i % len(queries)].replace(' ', '+')}&k=6") for i in range(n)],
                    conc,
                )
                ok = [ms for ms, code, _ in rows if code == 200]
                level[f"concurrency_{conc}"] = {**summarize(ok), "errors": sum(1 for _, code, _ in rows if code != 200)}
            plan = await self.sql(
                """
                EXPLAIN (FORMAT JSON) SELECT m.id FROM memories m
                JOIN memory_embeddings e ON e.ref_id = m.id AND e.table_ref = 'memories' AND e.model_key = $1
                WHERE m.status = 'active'
                ORDER BY e.embedding <=> (SELECT embedding FROM memory_embeddings WHERE model_key = $1 LIMIT 1)
                LIMIT 40
                """,
                FAKE_EMBED_KEY,
            )
            try:
                plan_json = json.loads(plan[0][0]) if plan else None
                node = plan_json[0]["Plan"] if plan_json else {}
                level["vector_leg_plan"] = {"node": node.get("Node Type"), "total_cost": node.get("Total Cost")}
                # find the scan under the sort
                stack = [node]
                scans = []
                while stack:
                    cur = stack.pop()
                    if "Scan" in str(cur.get("Node Type", "")):
                        scans.append(f"{cur.get('Node Type')} on {cur.get('Relation Name') or cur.get('Index Name')}")
                    stack.extend(cur.get("Plans", []))
                level["vector_leg_plan"]["scans"] = scans
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                level["vector_leg_plan"] = {"error": str(exc)}
            log(f"recall {total} active memories: c1 p50 {level['concurrency_1'].get('p50_ms')} ms, "
                f"c5 p95 {level['concurrency_5'].get('p95_ms')} ms, plan {level['vector_leg_plan']}")
            out["levels"].append(level)
        return out

    async def scenario_ambient(self) -> dict[str, Any]:
        n = self.args.ambient_events
        await self.patch_settings(
            ambient_enabled=True,
            default_model=self.args.model,
            ambient_routine_events_per_hour=max(n * 2, 20),
            ambient_runs_per_day=max(n * 2, 50),
        )
        name = f"{LOADGEN}-routine-{uuid.uuid4().hex[:6]}"
        resp = await self.http.post(
            f"{API}/routines",
            json={"name": name, "prompt": "Report the fired payload in one line.", "autonomy": "propose"},
        )
        if resp.status_code != 201:
            return {"error": f"POST /routines -> {resp.status_code} {resp.text[:300]}"}
        routine_id = resp.json()["id"]
        token = (await self.http.post(f"{API}/routines/{routine_id}/token")).json()["fire_token"]
        out: dict[str, Any] = {"routine": name, "events_fired": n}
        assert self.pg is not None
        sampler = Sampler(self.pg)
        sampler.start()
        t0 = time.perf_counter()

        async def fire(i: int) -> tuple[float, int]:
            s = time.perf_counter()
            r = await self.http.post(
                f"{API}/routines/{routine_id}/fire",
                json={"text": f"{LOADGEN} event {i}", "dedupe_key": f"{LOADGEN}-{uuid.uuid4().hex}"},
                headers={"Authorization": f"Bearer {token}"},
            )
            return (time.perf_counter() - s) * 1000, r.status_code

        fired = await self.bounded([fire(i) for i in range(n)], 10)
        codes: dict[str, int] = {}
        for _, code in fired:
            codes[str(code)] = codes.get(str(code), 0) + 1
        out["fire"] = {**summarize([ms for ms, _ in fired]), "codes": codes}
        accepted = codes.get("202", 0)
        # drain: pending events for this routine
        drain_s: float | None = None
        deadline = self.args.ambient_deadline
        while time.perf_counter() - t0 < deadline:
            pending = int(await self.sql_val(
                "SELECT count(*) FROM ambient_events WHERE routine_id = $1 AND verdict IS NULL", uuid.UUID(routine_id)
            ))
            if pending == 0:
                drain_s = round(time.perf_counter() - t0, 2)
                break
            await asyncio.sleep(1)
        out["drain"] = {
            "accepted": accepted,
            "drain_seconds": drain_s,
            "events_per_second": round(accepted / drain_s, 2) if drain_s else None,
            "timed_out": drain_s is None,
        }
        verdicts = await self.sql(
            "SELECT coalesce(verdict, 'pending') v, count(*) n FROM ambient_events WHERE routine_id = $1 GROUP BY 1",
            uuid.UUID(routine_id),
        )
        out["verdicts"] = {str(r["v"]): int(r["n"]) for r in verdicts}
        # runs to terminal
        runs_s: float | None = None
        while time.perf_counter() - t0 < deadline:
            rows = await self.sql(
                "SELECT status, count(*) n FROM runs WHERE trigger->>'routine_id' = $1 GROUP BY status", routine_id
            )
            st = {str(r["status"]): int(r["n"]) for r in rows}
            if st and not st.get("running") and not st.get("paused_hitl"):
                runs_s = round(time.perf_counter() - t0, 2)
                break
            if not st and drain_s is not None and out["verdicts"].get("fired", 0) == 0:
                break
            await asyncio.sleep(1)
        rows = await self.sql("SELECT status, count(*) n FROM runs WHERE trigger->>'routine_id' = $1 GROUP BY status", routine_id)
        out["runs"] = {"statuses": {str(r["status"]): int(r["n"]) for r in rows}, "all_terminal_after_s": runs_s}
        out["connections"] = await sampler.stop()
        log(f"ambient: fire codes {codes}, drain {drain_s}s, verdicts {out['verdicts']}, runs {out['runs']}")
        # teardown the routine (events/runs are cleaned by cleanup())
        await self.sql_exec("DELETE FROM ambient_events WHERE routine_id = $1", uuid.UUID(routine_id))
        r = await self.http.delete(f"{API}/routines/{routine_id}")
        out["routine_deleted"] = r.status_code == 204
        if r.status_code != 204:
            await self.sql_exec("DELETE FROM routines WHERE id = $1", uuid.UUID(routine_id))
        return out

    # ── cleanup ────────────────────────────────────────────────────

    async def cleanup(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        prefix, anywhere = f"{LOADGEN}%", f"%{LOADGEN}%"
        stmts: list[tuple[str, str, tuple[Any, ...]]] = [
            (
                "memory_embeddings",
                "DELETE FROM memory_embeddings WHERE model_key = $1::text "
                "OR ref_id IN (SELECT id FROM memories WHERE text LIKE $2::text)",
                (FAKE_EMBED_KEY, prefix),
            ),
            ("memories", "DELETE FROM memories WHERE text LIKE $1::text", (prefix,)),
            (
                "run_steps",
                "DELETE FROM run_steps WHERE run_id IN "
                "(SELECT id FROM runs WHERE chat_message LIKE $1::text OR chat_message LIKE $2::text)",
                (prefix, anywhere),
            ),
            (
                "runs",
                "DELETE FROM runs WHERE chat_message LIKE $1::text OR chat_message LIKE $2::text",
                (prefix, anywhere),
            ),
            (
                "conversations",
                "DELETE FROM conversations WHERE (title LIKE $1::text OR title LIKE $2::text) "
                "AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.conversation_id = conversations.id)",
                (prefix, anywhere),
            ),
        ]
        for table, stmt, params in stmts:
            try:
                out[table] = await self.sql_exec(stmt, *params)
            except Exception as exc:  # noqa: BLE001 — report, keep cleaning
                out[table] = f"error: {exc}"
        return out


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def to_markdown(report: dict[str, Any]) -> str:
    m = report["meta"]
    lines = [
        f"# Load baseline — {m['label']}",
        "",
        f"Captured {m['captured_at']} at commit `{m['git_sha']}` against `{m['base_url']}`, model `{m['model']}`.",
        f"Postgres `max_connections` = {report['at_rest']['max_connections']}; connections at rest = "
        f"{report['at_rest']['connections']['total']}.",
        "",
    ]
    sc = report["scenarios"]
    if "api" in sc and "endpoints" in sc["api"]:
        lines += ["## Read path at rest", "", "| endpoint | p50 ms | p95 ms | max ms | bytes | errors |", "|---|---|---|---|---|---|"]
        for name, s in sc["api"]["endpoints"].items():
            lines.append(f"| {name} | {s.get('p50_ms')} | {s.get('p95_ms')} | {s.get('max_ms')} | {s.get('bytes')} | {s.get('errors')} |")
        lines += ["", f"Peak connections during the sweep: {sc['api']['connections']['peak_connections']}", ""]
    if "runs-scale" in sc and "levels" in sc["runs-scale"]:
        lines += ["## Run-table growth", "", "| total runs | /runs p50 ms | /runs p95 ms | /runs bytes | /conversations p50 ms | /conversations p95 ms |", "|---|---|---|---|---|---|"]
        for lv in sc["runs-scale"]["levels"]:
            r, c = lv["GET /runs"], lv["GET /conversations"]
            lines.append(f"| {lv['total_runs']} | {r.get('p50_ms')} | {r.get('p95_ms')} | {r.get('bytes')} | {c.get('p50_ms')} | {c.get('p95_ms')} |")
        lines.append("")
    if "chat" in sc and "levels" in sc["chat"]:
        lines += [f"## Concurrent chat runs ({sc['chat']['model']})", "", "| concurrency | statuses | submit p95 ms | e2e p50 ms | e2e p95 ms | runs/s | peak conns |", "|---|---|---|---|---|---|---|"]
        for lv in sc["chat"]["levels"]:
            lines.append(f"| {lv['concurrency']} | {lv['statuses']} | {lv['submit'].get('p95_ms')} | {lv['end_to_end_completed'].get('p50_ms')} | {lv['end_to_end_completed'].get('p95_ms')} | {lv['throughput_runs_per_s']} | {lv['connections']['peak_connections']} |")
        lines.append("")
    if "sse" in sc:
        lines += ["## SSE subscribers", ""]
        for key in ("chat_stream", "ambient_stream"):
            s = sc["sse"].get(key) or {}
            if "levels" in s:
                lines += [f"### {s['path']}", "", "| streams open | probe ok/3 | probe p50 ms | db connections |", "|---|---|---|---|"]
                for lv in s["levels"]:
                    lines.append(f"| {lv['streams_open']} | {lv['probe']['ok']} | {lv['probe']['p50_ms']} | {lv['connections']['total']} |")
                lines += ["", f"Max streams with a healthy probe: **{s['max_streams_with_healthy_probe']}**; first failure at {s['first_failure_at_streams']}; recovery after close: {s['recovery_after_close_ms']} ms", ""]
            elif s:
                lines += [f"### {key}: {s.get('error')}", ""]
        if "paused_run" in sc["sse"]:
            lines += [f"Paused run: `{sc['sse']['paused_run']}`", ""]
    if "recall" in sc and "levels" in sc["recall"]:
        lines += ["## Memory recall by corpus size", "", "| active memories | c=1 p50 ms | c=1 p95 ms | c=5 p95 ms | vector leg plan |", "|---|---|---|---|---|"]
        for lv in sc["recall"]["levels"]:
            lines.append(f"| {lv['active_memories']} | {lv['concurrency_1'].get('p50_ms')} | {lv['concurrency_1'].get('p95_ms')} | {lv['concurrency_5'].get('p95_ms')} | {lv.get('vector_leg_plan', {}).get('scans')} |")
        lines.append("")
    if "ambient" in sc and "drain" in sc["ambient"]:
        a = sc["ambient"]
        lines += ["## Ambient backlog", "", f"Fired {a['events_fired']} webhook events: codes {a['fire']['codes']}, fire p95 {a['fire'].get('p95_ms')} ms.",
                  f"Drain of {a['drain']['accepted']} accepted events: {a['drain']['drain_seconds']} s ({a['drain']['events_per_second']} events/s); verdicts {a['verdicts']}.",
                  f"Runs: {a['runs']['statuses']}, all terminal after {a['runs']['all_terminal_after_s']} s; peak connections {a['connections']['peak_connections']}.", ""]
    for name, s in sc.items():
        if isinstance(s, dict) and "error" in s:
            lines += [f"## {name}: error", "", f"`{s['error']}`", ""]
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    h = Harness(args)
    await h.open()
    report: dict[str, Any] = {
        "meta": {
            "label": args.label,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "git_sha": git_sha(),
            "base_url": args.base_url,
            "model": args.model,
            "scenarios": args.scenarios,
            "args": {k: v for k, v in vars(args).items() if k not in {"database_url"}},
            "settings_before": h.settings_before,
        },
        "scenarios": {},
    }
    try:
        report["at_rest"] = await h.at_rest()
        log(f"at rest: {report['at_rest']}")
        runners = {
            "api": h.scenario_api,
            "runs-scale": h.scenario_runs_scale,
            "chat": h.scenario_chat,
            "sse": h.scenario_sse,
            "recall": h.scenario_recall,
            "ambient": h.scenario_ambient,
        }
        for name in args.scenarios:
            log(f"── scenario {name} ──")
            t0 = time.perf_counter()
            try:
                report["scenarios"][name] = await runners[name]()
            except Exception as exc:  # noqa: BLE001 — one scenario's failure is a result, not an abort
                log(f"scenario {name} failed: {exc!r}")
                report["scenarios"][name] = {"error": f"{type(exc).__name__}: {exc}"[:500]}
            report["scenarios"][name]["elapsed_s"] = round(time.perf_counter() - t0, 1)
    finally:
        if not args.keep_data:
            report["cleanup"] = await h.cleanup()
            log(f"cleanup: {report['cleanup']}")
        try:
            await h.restore_settings()
        except Exception as exc:  # noqa: BLE001
            report["restore_error"] = str(exc)
        report["at_rest_after"] = await h.at_rest()
        await h.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    md = out.with_suffix(".md")
    md.write_text(to_markdown(report) + "\n", encoding="utf-8")
    log(f"wrote {out} and {md}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--database-url", default="postgresql://concierge:concierge@localhost:5555/concierge")
    p.add_argument("--model", default=FAKE_MODEL, help="default_model for chat/sse/ambient runs")
    p.add_argument("--label", default="baseline")
    p.add_argument("--out", default="load-report.json")
    p.add_argument("--scenarios", default="api,runs-scale,chat,sse,recall,ambient",
                   type=lambda s: [x.strip() for x in s.split(",") if x.strip()])
    p.add_argument("--api-requests", type=int, default=100)
    p.add_argument("--api-concurrency", type=int, default=10)
    p.add_argument("--runs-sizes", default="1000,10000", type=lambda s: [int(x) for x in s.split(",")])
    p.add_argument("--runs-requests", type=int, default=15)
    p.add_argument("--chat-concurrency", default="5,10,25,50", type=lambda s: [int(x) for x in s.split(",")])
    p.add_argument("--chat-deadline", type=float, default=120.0)
    p.add_argument("--sse-step", type=int, default=5)
    p.add_argument("--sse-max", type=int, default=60)
    p.add_argument("--probe-timeout", type=float, default=5.0)
    p.add_argument("--recall-sizes", default="1000,10000,100000", type=lambda s: [int(x) for x in s.split(",")])
    p.add_argument("--recall-requests", type=int, default=40)
    p.add_argument("--ambient-events", type=int, default=40)
    p.add_argument("--ambient-deadline", type=float, default=300.0)
    p.add_argument("--keep-data", action="store_true")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(parse_args())))
