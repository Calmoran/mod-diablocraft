#pragma once
// What most Monk files include: the Monk's own entry points, the class helpers, the engine's records, sheet numbers,
// strike paths and tunables, and the core types a skill touches. A file includes this and only what it alone needs.
#include "dc_monk.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../common/dc_tunables.h"
#include "GameTime.h"
#include "Player.h"
#include "SpellAuras.h"
#include "Unit.h"

#include <algorithm>
#include <cstdint>
#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>
