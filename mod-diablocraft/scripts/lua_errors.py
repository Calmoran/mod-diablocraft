#!/usr/bin/env python3
"""Turn a Lua error drop file into readable errors (diablocraft-g74u4).

    python3 mod-diablocraft/scripts/lua_errors.py <dir>/<YYYY-MM-DD>/<Character>.txt

The drop (src/common/dc_lua_error_drop.cpp) writes BugSack's "send to player" whisper as it came, one line per addon
message: "HH:MM:SS BugSack[\\x01|\\x02|\\x03]\\t<text>". This joins AceComm's chunks back into sends (\\x01 first,
\\x02 next, \\x03 last; a bare prefix is a whole send), undoes AceSerializer (rev 1) and writes
<Character>.readable.txt beside the file: per error its time, message, stack, locals and how many times BugGrabber
counted it. The wire is docs/research/bugsack-wire.md (BugSack r225, !BugGrabber r154, AceComm-3.0 r6,
AceSerializer-3.0 r3). The raw file is left as it is.
"""
import re
import sys
from pathlib import Path

LINE = re.compile(r"^(\d\d:\d\d:\d\d) BugSack([\x01-\x03]?)\t(.*)$", re.S)
COLOUR = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")


def sends(lines):
    """[(clock of the last chunk, joined text)] and the problems met, from the drop file's lines."""
    out, problems, open_ = [], [], None
    for number, raw in enumerate(lines, 1):
        match = LINE.match(raw.rstrip("\n"))
        if not match:
            if raw.strip():
                problems.append(f"line {number}: not a BugSack chunk")
            continue
        clock, marker, text = match.groups()
        if marker in ("", "\x01") and open_ is not None:
            problems.append(f"line {number}: a send began before the last one ended (its last chunk never came)")
            open_ = None
        if marker == "":
            out.append((clock, text))
        elif marker == "\x01":
            open_ = [text]
        elif open_ is None:
            problems.append(f"line {number}: a chunk with no first chunk before it")
        elif marker == "\x02":
            open_.append(text)
        else:
            open_.append(text)
            out.append((clock, "".join(open_)))
            open_ = None
    if open_ is not None:
        problems.append("the last send never got its last chunk")
    return out, problems


def unescape(text):
    """AceSerializer's string escapes back to bytes (SerializeStringHelper / DeserializeStringHelper)."""
    def one(match):
        c = match.group(1)
        if c < "z":
            return chr(ord(c) - 64)
        return {"z": "\x1e", "{": "\x7f", "|": "~", "}": "^"}[c]
    return re.sub(r"~(.)", one, text, flags=re.S)


def number(text):
    value = float(text)
    return int(value) if value.is_integer() and re.fullmatch(r"-?\d+", text) else value


def deserialize(text):
    """The values one AceSerializer:Serialize(...) call wrote; tables come back as dicts (arrays as lists)."""
    text = re.sub(r"[\x00-\x1f\x7f ]", "", text)   # Deserialize strips control characters and spaces first
    tokens = re.findall(r"\^(.)([^^]*)", text)
    if not tokens or tokens[0] != ("1", ""):
        raise ValueError("not AceSerializer rev 1 data")
    position = 1

    def value():
        nonlocal position
        code, data = tokens[position]
        position += 1
        if code == "S":
            return unescape(data)
        if code == "N":
            return number(data)
        if code == "F":
            code2, exponent = tokens[position]
            position += 1
            if code2 != "f":
                raise ValueError("^F without its ^f")
            return float(data) * 2.0 ** int(exponent)
        if code in "Bb":
            return code == "B"
        if code == "Z":
            return None
        if code == "T":
            table = {}
            while tokens[position][0] != "t":
                key = value()
                table[key] = value()
            position += 1
            if table and sorted(table) == list(range(1, len(table) + 1)):
                return [table[i] for i in range(1, len(table) + 1)]
            return table
        raise ValueError(f"unknown type ^{code}")

    values = []
    while position < len(tokens) and tokens[position][0] != "^":
        values.append(value())
    return values


def parts(message):
    """(message, stack lines, locals lines) of one BugGrabber message: the stack and the Locals: block are inside it."""
    if isinstance(message, (list, dict)):   # over 980 bytes BugGrabber stores pieces (BugGrabber.lua:244-256)
        pieces = message if isinstance(message, list) else [message[k] for k in sorted(message)]
        message = "".join(str(p) for p in pieces)
    text = COLOUR.sub("", str(message))
    if text.endswith("\n  ---"):
        text = text[:-len("\n  ---")]
    text, _, locals_ = text.partition("\nLocals:")
    first, *stack = text.split("\n")
    return first, [l for l in stack if l.strip()], [l for l in locals_.split("\n") if l.strip()]


def readable(lines):
    """(the readable text of a drop file's lines, how many errors it holds)."""
    found, problems = sends(lines)
    blocks = []
    for clock, text in found:
        try:
            values = deserialize(text)
        except (ValueError, IndexError) as error:
            problems.append(f"the send of {clock} does not read: {error}")
            continue
        errors = values[0] if values else []
        for err in errors if isinstance(errors, list) else [errors]:
            if not isinstance(err, dict):
                continue
            first, stack, locals_ = parts(err.get("message", ""))
            head = (f"== {err.get('time', '?')}  x{err.get('counter', 1)}  ({err.get('type', 'error')}, "
                    f"session {err.get('session', '?')}, sent {clock})")
            block = [head, first]
            if stack:
                block += ["Stack:"] + ["  " + l.strip() for l in stack]
            if locals_:
                block += ["Locals:"] + ["  " + l.strip() for l in locals_]
            blocks.append("\n".join(block))
    count = len(blocks)
    if problems:
        blocks.append("\n".join(["== problems"] + problems))
    return "\n\n".join(blocks) + "\n", count


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    source = Path(argv[1])
    # split on \n only: str.splitlines would also break at \x85 or U+2028 inside an error's text
    text, count = readable(source.read_text(encoding="utf-8", errors="replace").split("\n"))
    target = source.with_name(source.stem + ".readable.txt")
    target.write_text(text, encoding="utf-8")
    print(f"{target}: {count} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
