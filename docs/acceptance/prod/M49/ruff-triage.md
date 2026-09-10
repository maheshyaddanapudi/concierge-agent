# Ruff BLE / S triage (M49)

Before M49 the ruff rule set was `E F I UP B SIM ASYNC`. The tree carried 69 `noqa: BLE001` and 2 `noqa: S608` markers suppressing rules that were **not enabled** — the real violation count was unknown until they ran. Enabling `BLE` (blind except) and `S` (bandit) surfaced **41 violations**:

| rule | count | what it flags |
|---|---|---|
| S101 | 31 | `assert` on a runtime path in `app/` — vanishes under `python -O` |
| BLE001 | 4 | blind `except Exception` with no suppression |
| S608 | 4 | SQL built with an f-string |
| S110 | 1 | `try/except/pass` |
| S314 | 1 | `xml.etree` parsing an untrusted RSS body |

## Decisions

| finding | sites | decision |
|---|---|---|
| S101 asserts used as type/None narrowing after structured-output calls and `session.get` | 31 | **Replaced with explicit checks that raise** (`TypeError` for a wrong structured-output type, `RuntimeError` for a row that vanished mid-operation, `EvalParseError` in the upload parser). The registry cache gained a typed `_rows()` boundary in place of eight identical asserts; the one assert on a column already selected `IS NOT NULL` became a defensive `continue`. |
| BLE001 without a marker: A2A card-refresh loop, A2A recheck, leader-lease heartbeat, the native summarizer's one repair retry | 4 | **Kept broad, justified in one line each.** Three are loops that must survive anything; the fourth catches adapter-specific parser/validation error types for a single repair retry. |
| S608 f-string SQL in memory recall and digest recall | 4 | **Suppressed with a justification on the string's closing line:** the spliced fragments are code constants (temporal predicate, scope filters, an exclusion clause); every value is a bound parameter. Same shape as the two pre-existing `api/runs.py` markers. |
| S110 `except: pass` in doclint's native-registry import probe | 1 | **Kept, justified:** offline lint, nothing to log to. |
| S314 `xml.etree.ElementTree.fromstring` on an RSS body | 1 | **Fixed:** `defusedxml` added as a dependency (with `types-defusedxml` for mypy strict); the parse call goes through `defusedxml.ElementTree`. The rest of the XML hardening — streamed body cap, parse off the event loop — stays in M52 as planned. |
| Existing `noqa: BLE001` markers with no justification text | 14 | **Justified in one line each** (e.g. "a broken probe never kills the tick", "redis invalidation is best-effort; Postgres is the truth"). |
| Tests | — | `tests/**` ignores S101/S105/S106/S108/BLE001: tests assert by nature and use throwaway credentials on purpose. `alembic/**` ignores S608: fixed DDL. |

## Surviving suppressions — every one carries a reason

| marker | count |
|---|---|
| `noqa: BLE001` (all with a one-line justification; `grep -rn "noqa: BLE001$" app` is empty) | 73 |
| `noqa: S608` | 6 |
| `noqa: … S110` | 4 |
| runtime `assert` statements left in `app/` | 0 |

## Executed proof

```
$ ruff check --select BLE,S --statistics app      # before M49 (from the working tree at 68eafb7)
31	S101  	assert
 4	BLE001	blind-except
 4	S608  	hardcoded-sql-expression
 1	S110  	try-except-pass
 1	S314  	suspicious-xml-element-tree-usage
Found 41 errors.

$ ruff check .                                     # after — BLE and S in the select list
All checks passed!

$ ruff format --check .
210 files already formatted

$ mypy app
Success: no issues found in 127 source files

$ grep -rn "noqa: BLE001$" app | wc -l         # bare markers left
0
```
