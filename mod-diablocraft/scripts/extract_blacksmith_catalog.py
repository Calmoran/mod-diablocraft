"""Read-only D3 MPQ discovery. Run via SSH stdin; never writes on the VPS.

StormLib ABI: https://github.com/ladislav-zezula/StormLib/blob/master/src/StormLib.h
D3 formats: supplied blizzless-diiis Core/MPQ/{SerializableData,FileFormats/GameBalance}.cs.
"""
import ctypes as c
import ctypes.util
import csv
import argparse
import hashlib
import json
import struct
import subprocess
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path('/home/user/diablocraft'))
args = parser.parse_args()
ROOT = args.repo / 'reference/blizzless-diiis'
MPQ = ROOT / 'src/DiIiS-NA/DataBase/MPQ'
lib = c.CDLL(ctypes.util.find_library('storm'))
HANDLE = c.c_void_p
DWORD = c.c_uint32
for name, args, result in [
    ('SFileOpenArchive', [c.c_char_p, DWORD, DWORD, c.POINTER(HANDLE)], c.c_bool),
    ('SFileCloseArchive', [HANDLE], c.c_bool),
    ('SFileOpenFileEx', [HANDLE, c.c_char_p, DWORD, c.POINTER(HANDLE)], c.c_bool),
    ('SFileGetFileSize', [HANDLE, c.POINTER(DWORD)], DWORD),
    ('SFileReadFile', [HANDLE, HANDLE, DWORD, c.POINTER(DWORD), HANDLE], c.c_bool),
    ('SFileCloseFile', [HANDLE], c.c_bool),
]:
    fn = getattr(lib, name)
    fn.argtypes, fn.restype = args, result


def read(archive, name):
    handle = HANDLE()
    if not lib.SFileOpenFileEx(archive, name.encode(), 0, c.byref(handle)):
        raise RuntimeError('Cannot open MPQ member: ' + name)
    try:
        high = DWORD()
        size = lib.SFileGetFileSize(handle, c.byref(high))
        if high.value or size > 64 * 1024 * 1024:
            raise RuntimeError('Unexpected member size: ' + name)
        buffer = c.create_string_buffer(size)
        got = DWORD()
        if not lib.SFileReadFile(handle, buffer, size, c.byref(got), None) or got.value != size:
            raise RuntimeError('Cannot read MPQ member: ' + name)
        return buffer.raw[:size]
    finally:
        lib.SFileCloseFile(handle)


handles = []
members = {}
summary = []
member_duplicates = []
blacksmith_table_sha256 = None
try:
    for path in sorted(MPQ.glob('*.mpq')):
        handle = HANDLE()
        # MPQ_OPEN_READ_ONLY = STREAM_FLAG_READ_ONLY (StormLib SDK).
        if not lib.SFileOpenArchive(str(path).encode(), 0, 0x100, c.byref(handle)):
            raise RuntimeError('Cannot open archive: ' + str(path))
        handles.append(handle)
        names = read(handle, '(listfile)').decode('utf-8', errors='strict').splitlines()
        for name in names:
            previous = members.get(name.lower())
            if previous and name.lower().endswith(('.gam', '.rcp')):
                if read(previous[0], previous[1]) != read(handle, name):
                    raise RuntimeError('Conflicting duplicate asset: ' + name)
                member_duplicates.append(name)
            members[name.lower()] = (handle, name, path.name)
        summary.append({'archive': path.name, 'members': len(names)})
    gam = [value for key, value in members.items() if key.endswith('.gam')]
    recipe = [value for key, value in members.items() if key.endswith('.rcp')]
    outputs = {}
    for handle, name, archive in recipe:
        data = read(handle, name)
        if len(data) < 32:
            raise RuntimeError('Short recipe asset: ' + name)
        sno = struct.unpack_from('<i', data, 16)[0]
        output = struct.unpack_from('<i', data, 28)[0]
        if sno in outputs and outputs[sno]['gbid'] != output:
            raise RuntimeError('Conflicting recipe SNO: ' + str(sno))
        outputs[sno] = {'gbid': output, 'asset': name, 'archive': archive,
                       'additional_affixes': struct.unpack_from('<i', data, 60)[0],
                       'additional_affixes_delta': struct.unpack_from('<i', data, 64)[0]}

    def hash_name(name):
        value = 0
        for letter in name.lower():
            value = (value * 33 + ord(letter)) & 0xffffffff
        return value if value < 0x80000000 else value - 0x100000000

    project = ROOT.parents[1]
    with (project / 'mod-diablocraft/data/d3/base_item_ids.csv').open(newline='', encoding='utf-8-sig') as stream:
        ids = {row['d3_id']: int(row['item_entry']) for row in csv.DictReader(stream)}
    with (project / 'mod-diablocraft/data/d3/base_items.csv').open(newline='', encoding='utf-8-sig') as stream:
        bases = {}
        for row in csv.DictReader(stream):
            hashed = hash_name(row['d3_id'])
            if hashed in bases and bases[hashed]['d3_id'] != row['d3_id']:
                raise RuntimeError('Mapped item hash collision')
            bases[hashed] = row
    items, types = {}, {}
    for handle, name, archive in gam:
        data = read(handle, name)
        if len(data) < 72:
            continue
        for index, stride in [(0, 336), (1, 1304)]:
            offset, size = struct.unpack_from('<ii', data, 40 + index * 16)
            if not size:
                continue
            if offset <= 0 or size % stride or offset + 16 + size > len(data):
                raise RuntimeError('Bad item table descriptor: ' + name)
            for pos in range(offset + 16, offset + 16 + size, stride):
                internal = data[pos:pos + 256].split(b'\0', 1)[0].decode('ascii')
                hashed = hash_name(internal)
                if index == 0:
                    types[hashed] = internal
                else:
                    items[hashed] = {'d3_id': internal,
                        'item_level': struct.unpack_from('<i', data, pos + 280)[0],
                        'required_level': struct.unpack_from('<i', data, pos + 332)[0],
                        'item_type_gbid': struct.unpack_from('<i', data, pos + 268)[0],
                        'base_quality': struct.unpack_from('<i', data, pos + 888)[0],
                        'set_sno': struct.unpack_from('<i', data, pos + 368)[0],
                        'source_asset': name, 'source_archive': archive}
    blacksmith = []
    tables = []
    for handle, name, archive in gam:
        data = read(handle, name)
        # Header = seven int32s; type and two flags then 16-byte descriptor slots.
        if len(data) < 448:
            continue
        offset, size = struct.unpack_from('<ii', data, 40 + 25 * 16)
        if size:
            if offset <= 0 or offset + 16 + size > len(data) or size % 336:
                tables.append({'name': name, 'archive': archive, 'offset': offset,
                               'size': size, 'problem': 'validate record stride'})
            else:
                rows = []
                for pos in range(offset + 16, offset + 16 + size, 336):
                    rowname = data[pos:pos + 256].split(b'\0', 1)[0].decode('ascii')
                    fields = struct.unpack_from('<8i', data, pos + 256)
                    ingredients = [struct.unpack_from('<2i', data, pos + 288 + i * 8) for i in range(6)]
                    rows.append({'name': rowname, 'fields': fields, 'ingredients': ingredients})
                    if name.lower().endswith('recipesblacksmith.gam') and fields[2] > 0:
                        output = outputs.get(fields[2])
                        base = bases.get(output['gbid']) if output else None
                        original = items.get(output['gbid']) if output else None
                        if original:
                            original['item_type'] = types.get(original['item_type_gbid'])
                        ingredient_records = []
                        for gbid, amount in ingredients:
                            if amount:
                                ingredient_records.append({'gbid': gbid, 'amount': amount,
                                    'd3_id': items.get(gbid, {}).get('d3_id')})
                        if fields[7] != len(ingredient_records):
                            raise RuntimeError('Ingredient count mismatch: ' + rowname)
                        if original and hash_name(original['d3_id']) != output['gbid']:
                            raise RuntimeError('Output identity mismatch: ' + rowname)
                        blacksmith_table_sha256 = hashlib.sha256(data).hexdigest()
                        blacksmith.append({'recipe': rowname, 'recipe_sno': fields[2],
                            'artisan_level': fields[5], 'gold': fields[6], 'flags': fields[4],
                            'ingredients': ingredient_records, 'original_item': original,
                            'output': output, 'd3_id': base['d3_id'] if base else None,
                            'wow_entry': ids.get(base['d3_id']) if base else None,
                            'name': base['d3_name'] if base else None,
                            'rarity': base['rarity'] if base else None,
                            'type': base['type'] if base else None,
                            'level_req': base['level_req'] if base else None,
                            'pool_version': base['pool_version'] if base else None})
                tables.append({'name': name, 'archive': archive, 'offset': offset,
                               'size': size, 'count': len(rows), 'sample': rows[:4]})
    matched = [row for row in blacksmith if row['wow_entry']]
    unmatched = [row for row in blacksmith if not row['wow_entry']]
    payload = {'archives': summary, 'gamebalance_files': len(gam),
                      'recipe_files': len(recipe), 'recipe_samples': [v[1] for v in recipe[:8]],
                      'recipe_tables': tables,
                      'coverage': {'recipe_rows': len(blacksmith), 'mapped': len(matched),
                          'unmapped': len(unmatched), 'missing_recipe_assets': sum(not row['output'] for row in blacksmith),
                          'missing_item_definitions': sum(not row['original_item'] for row in blacksmith),
                          'missing_ingredient_definitions': sum(not ingredient['d3_id'] for row in blacksmith for ingredient in row['ingredients']),
                          'unique_mapped_entries': len({row['wow_entry'] for row in matched}),
                          'unique_unmapped_output_ids': len({row['original_item']['d3_id'] for row in unmatched}),
                          'all_output_types': dict(Counter(row['original_item']['item_type'] for row in blacksmith)),
                          'mapped_rarities': dict(Counter(row['rarity'] for row in matched)),
                          'mapped_sample': matched[:3], 'unmapped_sample': unmatched[:3]},
                      'base_item_ids_sha256': hashlib.sha256((project / 'mod-diablocraft/data/d3/base_item_ids.csv').read_bytes()).hexdigest(),
                      'blacksmith_table_sha256': blacksmith_table_sha256,
                      'reference_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                      'identical_duplicate_assets': member_duplicates,
                      'recipes': blacksmith}
    print(json.dumps(payload, indent=2))
finally:
    for handle in handles:
        lib.SFileCloseArchive(handle)
