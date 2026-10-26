"""Append missing Blood Elf Warrior equipment rules to SkillRaceClassInfo.dbc.

Existing records and strings are preserved. Package the result for the client
and copy it into the server's DataDir/dbc before starting worldserver.
"""
from pathlib import Path
import struct
import sys

# Skills taught by the character-start weapon/shield/plate proficiency spells.
EQUIPMENT_SKILLS = (44, 172, 54, 160, 229, 43, 55, 136, 433, 173, 473, 293)


def add_proficiencies(raw):
    if len(raw) < 20:
        raise ValueError('Truncated SkillRaceClassInfo.dbc header')
    magic, count, fields, size, strings = struct.unpack_from('<4s4I', raw)
    if (magic, fields, size) != (b'WDBC', 8, 32) or len(raw) != 20 + count * size + strings:
        raise ValueError('Expected stock 3.3.5a SkillRaceClassInfo.dbc (eight uint32 fields)')
    rows = [struct.unpack_from('<8I', raw, 20 + i * size) for i in range(count)]
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError('Duplicate SkillRaceClassInfo record ID')
    next_id = max((r[0] for r in rows), default=0) + 1
    for skill in EQUIPMENT_SKILLS:
        candidates = [r for r in rows if r[1] == skill and (r[3] == 0 or r[3] & 1)]
        if not candidates:
            raise ValueError(f'Missing Warrior equipment skill rule: {skill}')
        if any(r[2] == 0 or r[2] & 512 for r in candidates):
            continue
        if len({r[4:] for r in candidates}) != 1:
            raise ValueError(f'Ambiguous Warrior equipment skill rules: {candidates}')
        # Restrict the copied rule to Blood Elf (512) and Warrior (1).
        rows.append((next_id, skill, 512, 1, *candidates[0][4:]))
        next_id += 1
    return (struct.pack('<4s4I', magic, len(rows), fields, size, strings)
            + b''.join(struct.pack('<8I', *r) for r in rows)
            + raw[20 + count * size:])


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'azerothcore-wotlk/build/server/data/dbc/SkillRaceClassInfo.dbc'
    output = Path(__file__).with_name('SkillRaceClassInfo.dbc')
    output.write_bytes(add_proficiencies(source.read_bytes()))
    print('Wrote', output, 'with Blood Elf Warrior equipment rules; existing rows preserved.')
