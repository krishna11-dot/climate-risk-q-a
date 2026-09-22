"""Custom static check for one specific, previously-real bug pattern in
this codebase: the same mutable object handed to two or more tasks that
run concurrently (via `asyncio.create_task` or `asyncio.gather`), without
a copy at each call site.

Why this exists instead of a ruff rule: ruff has no plugin system for
custom, project-specific rules (it's a single compiled Rust binary with a
fixed rule set) — that was actually claimed otherwise in an earlier
maintenance doc, which was wrong. This script is the practical
equivalent: an AST-based check, fast (no test execution, no LLM calls),
that runs as its own CI step, same spirit as a linter even though it
isn't one.

The bug this catches (see MAINTENANCE.md Round 1, bug #2): two agents
were both handed the *same* pipeline state object and scheduled
concurrently with `asyncio.create_task(...)`. Because they shared one
mutable object, each one's writes to it (e.g. cost tracking) clobbered
the other's instead of being independent. The fix was `.model_copy(deep=True)`
at each call site. This script flags any future instance of the same
shape of mistake, anywhere in the project — not just the one spot where
it was found and fixed.

What it does NOT try to be: a general-purpose data-flow or aliasing
analysis. It only understands this one shape: the same bare name (or
attribute/subscript chain rooted in the same name) passed as an argument
into two or more of `asyncio.create_task(...)` / `asyncio.gather(...)`
launch sites within the same function, without `.copy(...)`,
`.model_copy(...)`, or `copy.deepcopy(...)` wrapping it at that call
site. It will not catch the bug if it's introduced through an
intermediate variable, a class attribute stored earlier, or any other
indirection — a human reviewer is still needed for those.

Usage:
    python tools/check_shared_concurrent_state.py [path ...]

Exits 1 if any finding is reported, 0 otherwise (including when no
Python files are found), matching how a lint step should behave in CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_COPY_METHOD_NAMES = {"copy", "model_copy"}
_EXCLUDED_DIR_NAMES = {
    ".venv",
    ".venv-ragas",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}


def _is_copy_call(node: ast.AST) -> bool:
    """True if `node` is a call that produces an independent copy, e.g.
    `x.copy()`, `x.model_copy(deep=True)`, or `copy.deepcopy(x)`.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _COPY_METHOD_NAMES:
        return True
    if isinstance(func, ast.Attribute) and func.attr == "deepcopy":
        return True
    return isinstance(func, ast.Name) and func.id == "deepcopy"


def _find_risky_root_names(node: ast.AST) -> set[str]:
    """Finds the root variable names of any sub-expression in `node` that
    is passed through *without* being copied first.

    A "root name" is the leftmost identifier in an attribute/subscript
    chain (e.g. `state.rag_results` and `state` share root `state`,
    since both alias the same underlying mutable object).
    """
    if isinstance(node, ast.Name):
        return {node.id}

    if isinstance(node, ast.Attribute):
        return _find_risky_root_names(node.value)

    if isinstance(node, ast.Subscript):
        return _find_risky_root_names(node.value) | _find_risky_root_names(node.slice)

    if isinstance(node, ast.Call):
        if _is_copy_call(node):
            # Everything under the receiver (e.g. `state` in
            # `state.model_copy(...)`) is now independent — don't recurse
            # into it. Arguments to the copy call itself (rare, e.g.
            # `deep=True`) are still walked in case they somehow embed a
            # risky name, though in practice they never do.
            risky: set[str] = set()
            for arg in node.args:
                risky |= _find_risky_root_names(arg)
            for kw in node.keywords:
                risky |= _find_risky_root_names(kw.value)
            return risky

        # A generic call: the function/method being invoked isn't itself
        # a shared-state risk, only its arguments are.
        risky = set()
        for arg in node.args:
            risky |= _find_risky_root_names(arg)
        for kw in node.keywords:
            risky |= _find_risky_root_names(kw.value)
        return risky

    # Anything else (BinOp, IfExp, Tuple, List, Dict, comparisons, ...):
    # walk generic children so a risky name nested inside still surfaces.
    risky = set()
    for child in ast.iter_child_nodes(node):
        risky |= _find_risky_root_names(child)
    return risky


def _walk_shallow(node: ast.AST):
    """Like ast.walk, but does not descend into nested function/lambda
    bodies — those are checked independently as their own scope.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield from _walk_shallow(child)


def _launch_call_name(node: ast.Call) -> str | None:
    """Returns 'create_task' or 'gather' if `node` calls one of those
    (by attribute or bare name, regardless of import alias), else None.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:
        return None
    return name if name in ("create_task", "gather") else None


def _check_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef, filename: str
) -> list[str]:
    """Checks one function body for the shared-mutable-concurrent-state
    pattern and returns human-readable finding strings.
    """
    # Each "slot" is one thing that will run concurrently with the
    # others: one create_task(...) call, or one argument to a single
    # gather(...) call.
    slots: list[tuple[int, set[str]]] = []

    for stmt in func_node.body:
        for node in _walk_shallow(stmt):
            if not isinstance(node, ast.Call):
                continue
            launch_kind = _launch_call_name(node)
            if launch_kind == "create_task" and node.args:
                slots.append((node.lineno, _find_risky_root_names(node.args[0])))
            elif launch_kind == "gather":
                for arg in node.args:
                    slots.append((node.lineno, _find_risky_root_names(arg)))

    findings: list[str] = []
    reported: set[tuple[str, int, int]] = set()
    for i in range(len(slots)):
        for j in range(i + 1, len(slots)):
            line_i, names_i = slots[i]
            line_j, names_j = slots[j]
            for name in sorted(names_i & names_j):
                key = (name, line_i, line_j)
                if key in reported:
                    continue
                reported.add(key)
                findings.append(
                    f"{filename}:{line_i}: '{name}' is passed (without a copy) "
                    f"into a concurrent task here, and again at line {line_j} "
                    f"in the same function ({func_node.name}) - each task "
                    f"will share and mutate the same object. Wrap each "
                    f"argument in `.model_copy(deep=True)` (or `.copy()` / "
                    f"`copy.deepcopy(...)`) unless sharing is intentional."
                )
    return findings


def check_file(path: Path) -> list[str]:
    """Checks one Python source file and returns finding strings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_check_function(node, str(path)))
    return findings


def _iter_python_files(paths: list[str]):
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix == ".py":
            yield p
        elif p.is_dir():
            for f in p.rglob("*.py"):
                if not any(part in _EXCLUDED_DIR_NAMES for part in f.parts):
                    yield f


def main() -> int:
    targets = sys.argv[1:] or ["."]
    all_findings: list[str] = []
    for f in _iter_python_files(targets):
        all_findings.extend(check_file(f))

    for finding in all_findings:
        print(finding)

    if all_findings:
        print(f"\n{len(all_findings)} finding(s).")
        return 1
    print("No shared-mutable-concurrent-state issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
