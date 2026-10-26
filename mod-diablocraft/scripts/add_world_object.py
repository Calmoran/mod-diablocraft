"""Add one placeable world object with one command (diablocraft-jn9r), on top of generate_world_objects.py.

    python3 mod-diablocraft/scripts/add_world_object.py "World\\Generic\\PassiveDoodads\\ParticleEmitters\\AuraRed.m2" "Red Aura"
    python3 mod-diablocraft/scripts/add_world_object.py "<model path as Noggit shows it>" "<object name>" [--client-dir DIR] [--size 1]

The path is looked up in the stock GameObjectDisplayInfo first, then in our own display sheet; a hit REUSES that display (no new
display row, so no client DBC change and no new patch-4.MPQ). Otherwise the next free Torment display id (9700 and up) gets a row;
its size box is read from the model's .m2 header when --client-dir holds the extracted file, else it is zeros, flagged PLACEHOLDER
in the row's notes (the server reads the box only for interaction distance, which a decoration never asks). Either way a type 5
template takes the next free entry of the 910090-910099 block. Then the generator runs (client DBC and migration). Nothing is
spawned and nothing is built: a new display row still needs client-patch/build.sh, as the how-to in client-patch/dbc/README.md says.

--client-dir is a folder of EXTRACTED files (<dir>/World/.../Model.m2), not the client's MPQs.
"""
import argparse
import csv
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_world_objects as gen  # noqa: E402

FIRST_DISPLAY = gen.STOCK_MAX_DISPLAY + 76  # 9700, where Torment's own rows start
BOX_OFFSET = 0xA0  # M2 header: bounding_box (6 floats), then bounding_sphere_radius (read on the Cameras/*.m2 the server holds)


def key(path):
    """A model path the way the stock table writes it, lower-cased for comparing: backslashes, .mdx for .m2."""
    path = path.strip().replace("/", "\\").lstrip("\\")
    if path.lower().endswith(".m2"):
        path = path[:-3] + ".mdx"
    return path.lower()


def stock_display(model, store):
    """Lowest stock display id whose model is `model`, or None."""
    return min((i for i in store.rows if key(store.decode(i)["ModelName"]) == key(model)), default=None)


def read_box(client_dir, model):
    """(six box floats, file) of the model's .m2 under client_dir, or (None, None) when not given; ObjectError on a bad file."""
    if not client_dir:
        return None, None
    path = Path(client_dir)
    for part in (key(model)[:-4] + ".m2").split("\\"):  # the client's names are case-blind, Linux is not
        path = next((p for p in path.iterdir() if p.name.lower() == part), None) if path and path.is_dir() else None
    if path is None:
        raise gen.ObjectError(f"{model}: no .m2 under {client_dir} (give an extracted folder, or leave --client-dir out)")
    raw = path.read_bytes()
    if raw[:4] != b"MD20" or len(raw) < BOX_OFFSET + 28:
        raise gen.ObjectError(f"{path}: not an M2 model")
    *box, radius = struct.unpack_from("<6ff", raw, BOX_OFFSET)
    if not (all(box[i] <= box[i + 3] for i in range(3)) and radius >= 0):
        raise gen.ObjectError(f"{path}: its bounding box {box} is empty or inverted; fill the row's size box by hand")
    return box, path.name


def plan(model, name, display_rows, object_rows, store, client_dir=None, size=1.0):
    """(new display row or None, new object row, what it did). Pure: reads the sheets' rows, writes nothing."""
    if not model.strip() or not name.strip():
        raise gen.ObjectError("a model path and an object name are both needed")
    if any(r["name"].strip().lower() == name.strip().lower() for r in object_rows):
        raise gen.ObjectError(f"an object named {name!r} already exists in world_objects.csv")
    taken = {r["entry"] for r in object_rows}
    entry = next((e for e in gen.OBJECT_RANGE if e not in taken), None)
    if entry is None:
        raise gen.ObjectError(f"the object block {gen.OBJECT_RANGE.start}-{gen.OBJECT_RANGE.stop - 1} is full")
    new_display, display = None, stock_display(model, store)
    if display is not None:
        said = f"stock display {display}"
    elif (own := next((r for r in display_rows if key(r["model_path"]) == key(model)), None)) is not None:
        display, said = own["display_id"], f"our display {own['display_id']}"
    else:
        display = max([FIRST_DISPLAY - 1] + [r["display_id"] for r in display_rows]) + 1
        box, source = read_box(client_dir, model)
        note = (f"Size box read from the bounding box in {source}'s header (add_world_object.py)." if box else
                "PLACEHOLDER size box (add_world_object.py had no client folder): fill the six cells from the model's .m2 header "
                "and rerun generate_world_objects.py. The server reads the box only for interaction distance, which a decoration never asks.")
        new_display = dict(zip(["display_id", "model_path", "name", *gen.BOX, "notes"],
                               [display, key_as_stock(model), name, *(box or [0] * 6), note]))
        said = f"NEW display {display} (needs client-patch/build.sh)"
    obj = {"entry": entry, "display_id": display, "name": name, "size": size,
           "notes": f"Type 5 (generic, a decoration; nothing is spawned). Wears {said.split(' (')[0]}."}
    return new_display, obj, f"{name!r}: entry {entry} wears {said}"


def key_as_stock(model):
    """The path as the stock table writes it (.mdx), keeping the case the user gave."""
    path = model.strip().replace("/", "\\").lstrip("\\")
    return path[:-3] + ".mdx" if path.lower().endswith(".m2") else path


def append(path, row, columns):
    with Path(path).open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerow([row[c] for c in columns])


def add(model, name, stock_dir=gen.STOCK_DIR, display_source=gen.DISPLAYS, object_source=gen.OBJECTS, client_dir=None, size=1.0,
        run_generator=True):
    """Validates the sheets with the new rows first (a temp copy), then appends to the real ones and runs the generator."""
    store, display_rows = gen.stock_store(stock_dir), gen.displays(display_source)
    new_display, obj, said = plan(model, name, display_rows, gen.objects(display_rows, object_source, store.rows), store, client_dir, size)
    d_cols = ["display_id", "model_path", "name", *gen.BOX, "notes"]
    o_cols = ["entry", "display_id", "name", "size", "notes"]
    with tempfile.TemporaryDirectory(prefix="add_world_object_") as tmp:
        d, o = Path(tmp, "d.csv"), Path(tmp, "o.csv")
        d.write_bytes(Path(display_source).read_bytes())
        o.write_bytes(Path(object_source).read_bytes())
        if new_display:
            append(d, new_display, d_cols)
        append(o, obj, o_cols)
        gen.generate(stock_dir, d, o)  # raises ObjectError before anything real is touched
    if new_display:
        append(display_source, new_display, d_cols)
    append(object_source, obj, o_cols)
    if run_generator:
        error = gen.main(["--stock-dir", str(stock_dir)])
        if error:
            raise gen.ObjectError(error)
    return said


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", help="model path as Noggit shows it (.m2 or .mdx)")
    parser.add_argument("name", help="the object's name")
    parser.add_argument("--client-dir", help="folder of extracted client files, to read a new model's size box")
    parser.add_argument("--size", type=float, default=1.0, help="template scale (default 1)")
    parser.add_argument("--stock-dir", default=str(gen.STOCK_DIR))
    args = parser.parse_args(argv)
    try:
        print(add(args.model, args.name, args.stock_dir, client_dir=args.client_dir, size=args.size))
    except gen.ObjectError as error:
        return f"add_world_object: {error}"


if __name__ == "__main__":
    sys.exit(main())
