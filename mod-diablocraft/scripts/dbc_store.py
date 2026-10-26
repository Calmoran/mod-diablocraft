"""Reading and writing a DBC file as rows, and the SQL literal for one value.

Shared by the generators that project client DBC rows into a `*_dbc` server
table (class proficiencies, class resources, the trade skill retirement). It
began in the trade skill pilot's writer, which was retired with the pilot
(decisions.md 2026-10-03 R4); these three helpers are the part other generators
use.
"""
from pathlib import Path
import re
import struct


def schema(root, table):
    text = (root/'azerothcore-wotlk/data/sql/base/db_world'/f'{table}.sql').read_text()
    return re.findall(r'^  `([^`]+)` (\w+)([^\n]*)', text, re.M)


class Store:
    def __init__(self, raw, columns):
        magic, count, fields, size, strings = struct.unpack_from('<4s4I', raw)
        if magic != b'WDBC' or fields != len(columns) or size != fields*4 or len(raw) != 20+count*size+strings:
            raise ValueError('Invalid DBC layout')
        self.columns, self.size = columns, size
        self.block = bytearray(raw[20+count*size:])
        self.rows = {}
        for n in range(count):
            record = raw[20+n*size:20+(n+1)*size]
            key = struct.unpack_from('<I', record)[0]
            if key in self.rows:
                raise ValueError('Duplicate DBC identity')
            self.rows[key] = record

    def decode(self, key):
        raw = self.rows[key]
        values = {}
        for i, (name, kind, flags) in enumerate(self.columns):
            if kind in ('varchar', 'text'):
                offset, = struct.unpack_from('<I', raw, i*4)
                values[name] = self.block[offset:self.block.index(0, offset)].decode('utf-8')
            else:
                fmt = 'f' if kind == 'float' else ('I' if 'unsigned' in flags else 'i')
                values[name], = struct.unpack_from('<'+fmt, raw, i*4)
        return values

    def encode(self, values):
        record = bytearray(self.size)
        for i, (name, kind, flags) in enumerate(self.columns):
            value = values[name]
            if kind in ('varchar', 'text'):
                data = value.encode('utf-8')+b'\0'
                # Reuse full NUL-delimited strings, ensuring focused reruns do not grow.
                position = bytes(self.block).find(b'\0'+data)
                if not value:
                    offset = 0
                elif position >= 0:
                    offset = position+1
                else:
                    offset = len(self.block)
                    self.block.extend(data)
                struct.pack_into('<I', record, i*4, offset)
            else:
                fmt = 'f' if kind == 'float' else ('i' if value < 0 else 'I')
                struct.pack_into('<'+fmt, record, i*4, value)
        self.rows[values['ID']] = bytes(record)

    def bytes(self):
        return (struct.pack('<4s4I', b'WDBC', len(self.rows), len(self.columns), self.size, len(self.block))
                + b''.join(self.rows.values()) + self.block)


def sql_value(value):
    if isinstance(value, str):
        return "'"+value.replace('\\', '\\\\').replace("'", "''")+"'"
    return format(value, '.9g') if isinstance(value, float) else str(value)
