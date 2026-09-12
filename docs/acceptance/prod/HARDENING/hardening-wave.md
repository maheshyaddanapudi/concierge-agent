# hardening wave — 2026-09-11T22:32:05Z — model openrouter:qwen/qwen3.8-max

$ settings ← formatter on, evals on, a price override for the live model

$ A. the operator's wording survives a re-ingest (§3.2 description drift)
  before: {"description": "Echo the given text back.", "source": "server", "hash": "1833b073e7a3"}
  operator edit: {"description": "Operator: echoes the given word back - never anything else.", "source": "operator", "hash": "aa18a4ad7954"}
  after refresh-tools: {"description": "Operator: echoes the given word back - never anything else.", "source": "operator", "hash": "aa18a4ad7954"}

$ A. a tool_key rename is refused on a sanitized-name collision and while a skill mentions the old key
  rename add → demo-stub_echo (sanitizes like demo-stub.echo): 409
  skill hw-drill-skill: definition v1 hash=55dbd2741c8b
  rename echo → demo-stub.echo2 while the skill mentions {tool:demo-stub.echo}: skills mention {tool:demo-stub.echo} in their instructions: hw-drill-skill — update the mentions first

$ A. an MCP config edit is hashed, logged and reconnected at once
  patched: active last_connected_at 2026-09-11T22:32:08.925056Z
{"server_id": "9cd8d782-08ca-4ea8-b403-9a2c1f9092c2", "name": "demo-stub", "config_hash": "9ce6a5430c0f", "secrets_rotated": false, "changed_fields": ["args"], "event": "mcp_server_config_changed", "level": "warning", "timestamp": "2026-09-
{"server_id": "9cd8d782-08ca-4ea8-b403-9a2c1f9092c2", "tool_count": 5, "schema_changed": [], "content_changed": 0, "config_hash": "9ce6a5430c0f", "event": "mcp_tools_ingested", "level": "info", "timestamp": "2026-09-11T22:32:08.922450Z"}
  args restored

$ B. definition versions: a toggle is not a version, an edit is
  direct_exposure off: v1
  direct_exposure on:  v1
  persona edited:      v2

$ B. a run pins its settings, prompts, context and catalog slices; the formatter is a step; the cost is stamped
run 7766824b-e5ee-45d6-8a2c-401f01ddde20 → completed
  route             entity=hw-drill-skill version=2 model=None params=None
  skill             entity=hw-drill-skill version=2 model=openrouter:qwen/qwen3.8-max params=None
  format            entity=None version=None model=openrouter:qwen/qwen3.8-max params=None
  snapshot keys: ['build', 'catalog_calls', 'context', 'prompts', 's1', 'settings']
  settings.default_model=openrouter:qwen/qwen3.8-max prompts=24 files build=None
  context surfaces: ['planner'] catalog_calls=1
  cost_usd=0.00626 cost_priced=True price_snapshot={"prices": {"openrouter:qwen/qwen3.8-max": {"source": "override", "input_per_m": 1.0, "output_per_m": 2.0}}, "unpriced_tokens": 0}

$ B. the price doubles afterwards: the finished run does not move
  run cost before=0.00626 after=0.00626 price_snapshot input_per_m=1.0

$ C. the eval judge's own role and the overlap audit gate
  eval_judge_model=openrouter:qwen/qwen3.8-max: 200
  params without a model: 422 (422 like the other roles)
  registry_overlap_audit_enabled=yes: 422 (422)
  registry_overlap_audit_enabled=true: 200
  the audit job in the lifecycle map: registry:overlap_audit registry_overlap_audit_enabled 21600 s

$ restored
  skill deleted; formatter, evals, prices, judge and audit as before
