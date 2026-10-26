"""Every migration's string literals must be balanced, also the statements inside them (diablocraft-1itr).

loot_0011 wrote "quality''s" in a column COMMENT inside the doubled-quote string of a dynamic
`SET @dc_ddl = IF(..., 'ALTER ... COMMENT ''...''', 'DO 0')`. The outer literal is fine (`''` is one quote), but
it decodes to `COMMENT 'in this quality's bracket'`, and that closed the COMMENT early when PREPARE parsed it:
ERROR 1064, the updater stopped, the dev realm stayed down. Nothing parses a dynamic DDL until it runs, so this
tokenises each migration the way MySQL does (a string opened by ' or " must close before a line-ending `;` and
before the file does), then decodes every string literal that is itself a statement (ALTER, CREATE, ...) and
tokenises that again.

Run standalone; `DC_SQL_DIRS` (pathsep-separated) checks other directories instead of data/sql.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
STATEMENT = re.compile(r"\s*(ALTER|CREATE|DROP|INSERT|REPLACE|UPDATE|DELETE|SELECT)\b", re.I)
ESCAPE = re.compile(r"''|\\(.)", re.S)


def unbalanced(text: str) -> str | None:
    """Why `text` is not balanced (with the line a string opened on), or None."""
    quote, opened, line, i, n, start, inner = None, 0, 1, 0, len(text), 0, []
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
        if quote is None:
            if text.startswith("--", i) and text[i + 2:i + 3] in ("", " ", "\t", "\n", "\r") or c == "#":
                i = text.find("\n", i)
                i = n if i < 0 else i
                continue
            if text.startswith("/*", i):
                end = text.find("*/", i + 2)
                line += text[i:end if end >= 0 else n].count("\n")
                i = n if end < 0 else end + 2
                continue
            if c in "'\"`":
                quote, opened, start = c, line, i + 1
        elif c == "\\" and quote != "`":
            i += 1
        elif c == quote:
            if text[i + 1:i + 2] == quote:
                i += 1
            else:
                if quote == "'" and STATEMENT.match(text, start):
                    inner.append((opened, text[start:i]))
                quote = None
        elif c == ";" and text[i + 1:i + 2] in ("\n", "\r") and quote != "`":
            return f"a {quote} string opened on line {opened} is still open at the `;` ending line {line}"
        i += 1
    if quote:
        return f"a {quote} string opened on line {opened} never closes"
    for at, literal in inner:
        why = unbalanced(ESCAPE.sub(lambda m: m.group(1) or "'", literal))
        if why:
            return f"the statement in the string on line {at} decodes to unbalanced SQL: {why}"
    return None


class SqlQuotes(unittest.TestCase):
    def test_tokenizer_flags_both_shapes(self):
        stray = "SET @d=IF(@e=0,'A COMMENT ''x quality's bracket''','DO 0');\nPREPARE s FROM @d;\n"
        self.assertIn("still open", unbalanced(stray) or "")
        decoded = "SET @d='ALTER TABLE t COMMENT ''in this quality''s bracket''';\n"
        self.assertIn("decodes to unbalanced", unbalanced(decoded) or "")

    def test_tokenizer_passes_balanced_sql(self):
        self.assertIsNone(unbalanced("SET @d='ALTER TABLE t COMMENT ''in this qualitys bracket''';\n"))
        self.assertIsNone(unbalanced("INSERT INTO t VALUES ('Zul''jin', 'a\\'b');\n"))
        self.assertIsNone(unbalanced("-- it's a comment\nSELECT 'a''b', \"c\\\"d\", `e`; /* don't */\n"))

    def test_every_migration_is_balanced(self):
        override = os.environ.get("DC_SQL_DIRS")
        roots = [Path(p) for p in override.split(os.pathsep) if p] if override else [MODULE / "data" / "sql"]
        files = sorted(f for root in roots for f in root.rglob("*.sql"))
        self.assertTrue(files, "no .sql files found")
        bad = {f.name: why for f in files if (why := unbalanced(f.read_text(encoding="utf-8")))}
        self.assertEqual(bad, {})


if __name__ == "__main__":
    sys.exit(unittest.main())
