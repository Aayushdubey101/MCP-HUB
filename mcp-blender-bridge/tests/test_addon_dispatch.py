"""Regression test: every cmd_* function in the addon is in COMMAND_HANDLERS."""

from __future__ import annotations

import ast
import pathlib


def test_every_cmd_function_is_in_dispatch_table() -> None:
    src = pathlib.Path("blender_addon/mcp_blender_bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    cmd_fns = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("cmd_")
    }

    handler_values: set[str] = set()
    for node in ast.walk(tree):
        # COMMAND_HANDLERS uses an annotated assignment: `COMMAND_HANDLERS: dict[str, Any] = {...}`
        dict_node = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "COMMAND_HANDLERS":
                    dict_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "COMMAND_HANDLERS":
                dict_node = node.value
        if isinstance(dict_node, ast.Dict):
            for v in dict_node.values:
                if isinstance(v, ast.Name):
                    handler_values.add(v.id)

    unregistered = cmd_fns - handler_values
    assert not unregistered, f"cmd_ functions not in COMMAND_HANDLERS: {unregistered}"
