# Prompt regression harness — executed proof (M49)

Captured 2026-09-01T22:21:32Z at commit `68eafb7` (working tree with the M49 changes).

## 1. The shipped prompts pass their golden sets

```
$ python -m app.prompts.check
prompt golden sets: 24 prompts, 24 cases, 0 failed
exit=0
```

## 2. A deliberate regression fails the harness

Two edits a careless prompt change could make: the planner's refusal contract loses its `no_confident_match` sentence, and the router prompt renames `{conditions}` to `{choices}` while the consumer still passes `conditions`.

```
$ sed -i "s/no_confident_match/no_match_found/" app/prompts/planner.md
$ sed -i "s/{conditions}/{choices}/" app/prompts/router.md
$ python -m app.prompts.check
FAIL planner [refusal_and_shape_contract]
     - must_contain missing: 'set no_confident_match to true'
FAIL router [pick_index]
     - placeholder(s) ['choices'] in the file are not supplied by the case — the consumer's .format() would raise KeyError
prompt golden sets: 24 prompts, 24 cases, 2 failed
exit=1
```

Prompts restored (`git checkout -- app/prompts/planner.md app/prompts/router.md`); the harness is green again:

```
prompt golden sets: 24 prompts, 24 cases, 0 failed
exit=0
```

## 3. The pytest gate

```
$ pytest tests/test_prompt_golden.py -q
.......                                                                  [100%]
7 passed in 1.96s
```

## 4. A prompt with no consumer

The harness requires every golden set to name the module that loads its prompt, and checks that module really calls `load_prompt("<stem>")`. Applying that rule to the shipped tree found `answer_ui.md`: no module loaded it — the M8/M24 formatter role (`formatter.md`) had replaced it. It was removed in M49 rather than given a golden set.
