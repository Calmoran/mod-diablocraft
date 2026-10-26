"""diablocraft-ho3ww: a rift floor loads its grids on demand (core patch 0026), and its doors still open.

The stock Map::OnCreateMap loaded every grid and navmesh tile of a new instance on the world thread inside the rift quest
accept; over 30 s under load the freeze detector killed dev. The module answers core patch 0026's
IsInstanceLoadedOnDemand for the rift floor it is opening (the opening's map and instance id, set by
OnBeforeCreateInstanceScript, which runs first) and for an open-zone copy (a whole continent). OpenDoors (4.13) opens
the doors of the grids loaded when the floor opens; LateDoors opens any other door of that floor when its grid loads.

Wiring checks on the module source, each with the single-rule mutant that must break it.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402

SRC = Path(__file__).resolve().parents[3] / "src/rifts"
RIFTS = rifts_text()
SPAWNER = (SRC / "dc_rift_spawner.cpp").read_text(encoding="utf-8")
CORE_CREATE = Path(__file__).resolve().parents[4] / "azerothcore-wotlk/src/server/game/Maps/MapInstanced.cpp"


def body(text, signature):
    start = text.index(signature)
    open_ = text.index("{", start)
    depth = 0
    for i in range(open_, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[open_:i + 1]
    raise ValueError(signature)


def problems(rifts, spawner):
    out = []
    script = body(rifts, "class RiftMap final : public AllMapScript")
    ctor = script.split("bool IsInstanceLoadedOnDemand")[0]
    if "ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND" not in ctor:
        out.append("RiftMap does not enable the hook, so the core never asks it")
    if "bool IsInstanceLoadedOnDemand(Map* map) override" not in script:
        out.append("RiftMap does not answer the hook")
    else:
        answer = body(script, "bool IsInstanceLoadedOnDemand(Map* map) override")
        rule = re.sub(r"\s+", " ", answer)
        if ("opening && opening->mapId == map->GetId() && opening->instanceId == map->GetInstanceId()" not in rule):
            out.append("on demand is not the opening rift's own instance")
        if "|| IsOpenZoneMap(map->GetId())" not in rule:
            out.append("an open-zone copy still preloads the whole continent")
    before = body(rifts, "void OnBeforeCreateInstanceScript(InstanceMap* map")
    if "rift.instanceId = map->GetInstanceId();" not in before:
        out.append("the opening rift's instance id is not set before the core asks")

    mark = body(spawner, "struct FloorMark : public DataMap::Base")
    if "bool doorsOpen = false;" not in mark:
        out.append("no doors-open mark on the floor")
    floor = body(spawner, "void OpenFloor(Map* map, unsigned tier)")
    if "record->doors = OpenDoors(map);\n        mark->doorsOpen = true;" not in floor:
        out.append("the floor is not marked once OpenDoors has run")
    if "class LateDoors final : public AllGameObjectScript" not in spawner:
        out.append("no late-door script")
    else:
        late = body(spawner, "void OnGameObjectAddWorld(GameObject* go) override")
        if "go->GetGoType() != GAMEOBJECT_TYPE_DOOR" not in late:
            out.append("a late object opens whatever its type")
        if 'CustomData.Get<FloorMark>("DCRiftSpawner")' not in late or "if (mark->doorsOpen)" not in late:
            out.append("a late door opens on a floor that has not opened its doors")
        if "go->SetGoState(GO_STATE_ACTIVE);" not in late:
            out.append("a late door is not opened")
    if "new LateDoors();" not in body(spawner, "void RegisterScripts()"):
        out.append("LateDoors is not registered")
    return out


MUTANTS = {
    "hook not enabled": ("rifts", "ALLMAPHOOK_ON_MAP_UPDATE, ALLMAPHOOK_IS_INSTANCE_LOADED_ON_DEMAND})", "ALLMAPHOOK_ON_MAP_UPDATE})"),
    "any instance of the rift's map": ("rifts", " && opening->instanceId == map->GetInstanceId()", ""),
    "open-zone copies preload": ("rifts", " ||\n                   IsOpenZoneMap(map->GetId());", ";"),
    "doors marked before they open": ("spawner", "        record->doors = OpenDoors(map);\n        mark->doorsOpen = true;\n",
                                      "        mark->doorsOpen = true;\n        record->doors = OpenDoors(map);\n"),
    "every late object opens": ("spawner", "if (go->GetGoType() != GAMEOBJECT_TYPE_DOOR)\n                    return;\n", ""),
    "late doors on any floor": ("spawner", "if (mark->doorsOpen)", "if (mark)"),
    "late doors stay shut": ("spawner", "go->SetGoState(GO_STATE_ACTIVE);", "go->SetGoState(GO_STATE_READY);"),
    "not registered": ("spawner", "        new LateDoors();\n", ""),
}


class OnDemand(unittest.TestCase):
    def test_the_wiring_holds(self):
        self.assertEqual(problems(RIFTS, SPAWNER), [])

    def test_every_mutant_is_refused(self):
        for name, (which, old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                text = RIFTS if which == "rifts" else SPAWNER
                self.assertEqual(text.count(old), 1, name)
                text = text.replace(old, new)
                found = problems(text, SPAWNER) if which == "rifts" else problems(RIFTS, text)
                self.assertNotEqual(found, [], "mutant survived: " + name)

    def test_the_core_asks_after_the_instance_script_hook(self):
        # MapInstanced::CreateInstance: CreateInstanceScript (which runs OnBeforeCreateInstanceScript) before
        # OnCreateMap, where 0026 asks; the opening's instance id is set by then.
        create = body(CORE_CREATE.read_text(encoding="utf-8"), "InstanceMap* MapInstanced::CreateInstance(")
        self.assertLess(create.index("map->CreateInstanceScript("), create.index("map->OnCreateMap();"))


if __name__ == "__main__":
    unittest.main()
