"""Every `INSERT INTO dc_item_affix` must have one column, one placeholder and one argument per value.

G1's blocker: `AffixRow` (src/crafting/dc_crafting_shared.cpp) named 11 columns but wrote 10 placeholders, so
the statement sent 10 values with range_max2 quoted as a string and `kind` unquoted - MySQL refused
it and every Mystic replacement that copies an affix failed its transaction. The shape is mechanical
and silent, so this checks it for every such INSERT in the module.

Run standalone; `DC_ARITY_FILES` (pathsep-separated) checks specific files instead of all of src.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
SRC = MODULE / "src"
INSERT = "INSERT INTO dc_item_affix"


def append_calls(text: str) -> list[list[str]]:
    """The `Append(` call around each INSERT, split into top-level arguments."""
    out = []
    for match in re.finditer(re.escape(INSERT), text):
        start = text.rfind("Append(", 0, match.start())
        assert start != -1, "an INSERT INTO dc_item_affix with no Append( before it"
        depth, index, args, buf, quoted = 1, start + len("Append("), [], [], None
        while index < len(text) and depth:
            char = text[index]
            if quoted:
                buf.append(char)
                if char == "\\":
                    index += 1
                    buf.append(text[index])
                elif char == quoted:
                    quoted = None
            elif char in "\"'":
                quoted = char
                buf.append(char)
            elif char == "(":
                depth += 1
                buf.append(char)
            elif char == ")":
                depth -= 1
                if depth == 0:
                    args.append("".join(buf))
                    break
                buf.append(char)
            elif char == "," and depth == 1:
                args.append("".join(buf))
                buf = []
            else:
                buf.append(char)
            index += 1
        out.append(args)
    return out


def sql_of(argument: str) -> str:
    """The C++ string literals of one argument, joined as the client will."""
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', argument))


def values_items(sql: str) -> list[str]:
    """The VALUES list split into its items - a placeholder or a literal each."""
    start = sql.index("VALUES")
    open_, depth, items, buf, quoted = sql.index("(", start), 1, [], [], None
    for char in sql[open_ + 1:]:
        if quoted:
            buf.append(char)
            if char == quoted:
                quoted = None
        elif char in "\"'":
            quoted = char
            buf.append(char)
        elif char == "(":
            depth += 1
            buf.append(char)
        elif char == ")":
            depth -= 1
            if depth == 0:
                items.append("".join(buf).strip())
                break
            buf.append(char)
        elif char == "," and depth == 1:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    return items


def main() -> int:
    override = os.environ.get("DC_ARITY_FILES")
    files = ([Path(p) for p in override.split(os.pathsep) if p] if override
             else sorted(SRC.rglob("*.cpp")))
    checked, failures = 0, []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for args in append_calls(text):
            sql = sql_of(args[0])
            columns = sql[sql.index("(", sql.index(INSERT)) + 1:sql.index(")")]
            count = len([c for c in columns.split(",") if c.strip()])
            items = values_items(sql)
            placeholders = len([item for item in items if "{}" in item])
            arguments = len(args) - 1
            checked += 1
            # One column per VALUES item, and one argument per placeholder (a literal item takes
            # none); a short VALUES list or a stray argument is how the G1 fault read.
            if count != len(items) or arguments != placeholders:
                failures.append(f"{path.name}: {count} columns, {len(items)} VALUES items, "
                                f"{placeholders} placeholders, {arguments} arguments:\n    {sql}")
    if failures:
        print("FAIL affix insert arity:\n" + "\n".join(failures))
        return 1
    print(f"PASS affix insert arity: {checked} INSERT INTO dc_item_affix statement(s) each name one "
          f"column per placeholder per argument")
    return 0


if __name__ == "__main__":
    sys.exit(main())
