"""Validate generated currencies against the local stock DBCs, without writing."""
import struct

import build_currencytypes as builder


def main():
    stock, strings = builder.read_dbc(builder.DEFAULT_SOURCE)
    actual, actual_strings = builder.read_dbc(builder.OUTPUT)
    # The existing writer sorts by row ID; stock file storage order may differ.
    assert actual[:len(stock)] == sorted(stock), 'Stock currency rows changed'
    assert actual_strings == strings, 'Stock string block changed'
    expected = [(row_id, entry, 1, 30 + i)
                for i, (row_id, entry, _) in enumerate(builder.CURRENCIES)]
    assert actual[len(stock):] == expected, 'Custom IDs, categories or bit indices changed'
    for column in (0, 1, 3):
        values = [row[column] for row in actual]
        assert len(values) == len(set(values)), 'Duplicate currency index'
    assert all(1 <= row[3] <= 64 for row in actual)

    category_file = builder._SERVER_DBC.with_name('CurrencyCategory.dbc')
    data = category_file.read_bytes()
    magic, count, fields, size, string_size = struct.unpack_from('<4s4I', data)
    assert (magic, fields, size) == (b'WDBC', 19, 76)
    assert len(data) == 20 + count * size + string_size
    strings = data[20 + count * size:]
    categories = {}
    for index in range(count):
        category, flags, offset = struct.unpack_from('<3I', data, 20 + index * size)
        categories[category] = (flags, strings[offset:].split(b'\0', 1)[0])
    assert categories[builder.CATEGORY] == (0, b'Miscellaneous'), categories
    assert categories[3] == (3, b'Unused'), categories
    print(f'PASS: 26 stock rows preserved; {len(builder.CURRENCIES)} unique currencies retain IDs/bits;')
    print('PASS: category 1 is Miscellaneous (flags 0), category 3 is Unused (flags 3)')


if __name__ == '__main__':
    main()
