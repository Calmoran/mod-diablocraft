// Torment's extension module on wxl-core (client-extension/wxl-core, pinned at 748d77b).
//
// wxl-core loads it from Extensions\Torment\Torment.dll at engine init
// (wxl-core/src/runtime/Extensions.cpp LoadAll/LoadOne). The CI job copies this folder to
// wxl-core/extensions/Torment, so upstream's own extension loop builds it; nothing here is
// built on its own.
//
// The manifest is the WXL_PluginInfo block WXL_Query returns: the loader reads it before any of
// our code runs and refuses a module built for another API version or client build.
//
// Key state (C2, docs/contracts/client-key-state.md): wxl's OnInput hands every client window
// message to a key table (KeyTable.hpp), and one read-only Lua global, TormentKeyDown, answers from
// it. The module only reads input: it never consumes a message, sends a key or casts.
//
// Class patches (Monk 1c, docs/contracts/monk-class.md): tswow's three class patches (ClassPatches.hpp),
// written into the client's code when the module loads instead of into Wow.exe's file.
//
// Damage text (docs/contracts/damage-text.md): the engine's own floating numbers and words, for the hits it
// would draw them for, handed to the addon through two read-only Lua globals, TormentDamageTextRead and
// TormentWorldToScreen (DamageText.hpp, DamageTextSites.hpp). While the addon reads, the engine draws nothing
// for those hits; when it stops, the engine draws them again.

#include "ClassPatches.hpp"
#include "DamageText.hpp"
#include "DamageTextSites.hpp"
#include "KeyTable.hpp"

#include "common/Mem.hpp"
#include "engine/events/Event.hpp"
#include "game/Script.hpp"
#include "game/World.hpp"
#include "wxl/PluginApi.h"

#include <windows.h>

#include <cstring>
#include <iterator>
#include <type_traits>

namespace
{
    namespace ev = wxl::events;
    namespace script = wxl::game::script;

    constexpr uint32_t kTormentModuleVersion = 4;
    constexpr char kKeyDownGlobal[] = "TormentKeyDown";
    constexpr char kDamageTextReadGlobal[] = "TormentDamageTextRead";
    constexpr char kWorldToScreenGlobal[] = "TormentWorldToScreen";

    const WXL_PluginInfo kInfo = {
        sizeof(WXL_PluginInfo), WXL_API_VERSION, "Torment", kTormentModuleVersion, WXL_CLIENT_BUILD,
    };

    const WXL_Api* g_api = nullptr;
    torment::KeyTable g_keys;
    bool g_registered = false;

    script::ValidateCallbackFn g_validate = nullptr;
    script::InterfaceLoadFn g_interfaceLoad = nullptr;

    namespace cp = torment::class_patches;

    /// The class role table the client reads once 'class roles' points it here (ClassPatches.hpp).
    uint8_t g_roles[cp::kRoleEntries] = {};

    bool WriteEdits(const cp::Edit* edits, size_t count)
    {
        bool ok = true;
        for (size_t i = 0; i < count; ++i)
            ok = wxl::mem::Patch(reinterpret_cast<void*>(edits[i].va), edits[i].bytes, edits[i].len) && ok;
        return ok;
    }

    /// Moves the role table into g_roles: the stock entries copied, every site pointed at the copy. All five
    /// sites must name one table, or this is not the build the offsets are for and nothing is written.
    bool MoveRoleTable()
    {
        const uint32_t stock = wxl::mem::Read<uint32_t>(cp::kRoleTableSites[0]);
        for (uintptr_t site : cp::kRoleTableSites)
            if (wxl::mem::Read<uint32_t>(site) != stock)
                return false;
        std::memcpy(g_roles, reinterpret_cast<const void*>(static_cast<uintptr_t>(stock)), cp::kStockRoleEntries);
        const uint32_t moved = static_cast<uint32_t>(reinterpret_cast<uintptr_t>(g_roles));
        bool ok = true;
        for (uintptr_t site : cp::kRoleTableSites)
            ok = wxl::mem::Patch(reinterpret_cast<void*>(site), &moved, sizeof(moved)) && ok;
        return ok;
    }

    /// Runs from WXL_Load, inside wxl's engine-init detour before the engine goes on
    /// (wxl-core/src/runtime/Extensions.cpp EngineInitDetour): before GlueXML loads, the create screen runs
    /// or LFG reads a role, so every byte is in place before the code that reads it.
    void ApplyClassPatches()
    {
        const struct
        {
            const char* name;
            bool ok;
        } parts[] = {
            {"custom GlueXML", WriteEdits(cp::kGlueXml, std::size(cp::kGlueXml))},
            {"race/class pairs", WriteEdits(cp::kRaceClassPairs, std::size(cp::kRaceClassPairs))},
            {"class roles", MoveRoleTable()},
        };
        for (const auto& part : parts)
            g_api->Log(part.ok ? WXL_LOG_INFO : WXL_LOG_ERROR, "torment", "class patch %s: %s", part.name,
                       part.ok ? "applied" : "FAILED");
    }

    namespace dt = torment::damage_text;
    namespace sites = torment::damage_text_sites;

    dt::Queue g_hits;
    dt::Reader g_reader;
    /// All four damage text hooks are in place, so the two globals may go up.
    bool g_damageTextHooked = false;

    sites::AddWorldDamageTextFn g_addWorldDamageText = nullptr;
    sites::AddWorldTextFn g_addWorldText = nullptr;
    sites::AddWorldHealingTextFn g_addWorldHealingText = nullptr;
    sites::CreateWorldTextFn g_createWorldText = nullptr;

    /// The hit an AddWorld* call is deciding, for CreateWorldText to queue; null outside those calls. Main
    /// thread only, as the engine's combat log is.
    struct Pending
    {
        void* unit;
        dt::Hit hit;
    };
    Pending* g_pending = nullptr;

    /// Holds a hit as pending for the length of one AddWorld* call.
    class PendingScope
    {
    public:
        PendingScope(void* unit, const uint64_t* source, dt::Kind kind, int32_t amount, const void* spell, bool crit,
                     bool periodic)
        {
            pending_.unit = unit;
            dt::Hit& hit = pending_.hit;
            hit.kind = kind;
            // The packet's field is unsigned; the engine passes it on as a signed int.
            hit.amount = static_cast<uint32_t>(amount);
            hit.school = spell ? *reinterpret_cast<const uint32_t*>(static_cast<const char*>(spell) +
                                                                     sites::kSpellSchoolMask)
                               : dt::kNoSpellSchool;
            hit.crit = crit;
            hit.periodic = periodic;
            hit.own = source && *source == wxl::game::world::ActivePlayerGuid();
            g_pending = &pending_;
        }
        ~PendingScope()
        {
            g_pending = nullptr;
        }
        PendingScope(const PendingScope&) = delete;
        PendingScope& operator=(const PendingScope&) = delete;

    private:
        Pending pending_{};
    };

    void __fastcall AddWorldDamageText(void* unit, void* edx, const uint64_t* source, int32_t amount, const void* spell,
                                       bool crit, bool periodic, bool spellColor)
    {
        PendingScope scope(unit, source, dt::Kind::Damage, amount, spell, crit, periodic);
        g_addWorldDamageText(unit, edx, source, amount, spell, crit, periodic, spellColor);
    }

    void __fastcall AddWorldText(void* unit, void* edx, const uint64_t* source, int32_t reason, const void* spell,
                                 bool periodic)
    {
        PendingScope scope(unit, source, dt::Kind::Word, 0, spell, false, periodic);
        g_addWorldText(unit, edx, source, reason, spell, periodic);
    }

    void __fastcall AddWorldHealingText(void* unit, void* edx, const uint64_t* source, int32_t amount,
                                        const void* spell, bool crit, int32_t unused)
    {
        PendingScope scope(unit, source, dt::Kind::Heal, amount, spell, crit, false);
        g_addWorldHealingText(unit, edx, source, amount, spell, crit, unused);
    }

    /// Reached only once the engine has decided to draw: a pending hit goes to the queue instead while the
    /// addon reads. Anything else (another world text, or the addon not reading) is the engine's as before.
    void __fastcall CreateWorldText(void* nameDesc, void* edx, uint32_t type, const char* text, const void* color,
                                    const int32_t* pvpRank)
    {
        Pending* pending = g_pending;
        if (pending && g_reader.Reading(GetTickCount()))
        {
            g_pending = nullptr; // one text per AddWorld* call
            dt::Hit hit = pending->hit;
            float position[3];
            wxl::game::world::NamePosition(pending->unit, position);
            hit.x = position[0];
            hit.y = position[1];
            hit.z = position[2] - sites::kTextStartDrop;
            if (hit.kind == dt::Kind::Word)
                hit.SetWord(text);
            g_hits.Push(hit);
            return;
        }
        g_createWorldText(nameDesc, edx, type, text, color, pvpRank);
    }

    constexpr const char* KindName(dt::Kind kind)
    {
        switch (kind)
        {
            case dt::Kind::Heal:
                return "heal";
            case dt::Kind::Word:
                return "word";
            default:
                return "damage";
        }
    }

    /// TormentDamageTextRead(): the oldest queued hit as kind, amount, school, crit, periodic, own, x, y, z,
    /// word; nil when there is none. Every call counts as the addon reading.
    int __cdecl DamageTextRead(void* state)
    {
        g_reader.MarkRead(GetTickCount());
        dt::Hit hit;
        if (!g_hits.Pop(hit))
        {
            script::PushNil(state);
            return 1;
        }
        script::PushString(state, KindName(hit.kind));
        script::PushNumber(state, hit.amount);
        script::PushNumber(state, hit.school);
        script::PushBoolean(state, hit.crit);
        script::PushBoolean(state, hit.periodic);
        script::PushBoolean(state, hit.own);
        script::PushNumber(state, hit.x);
        script::PushNumber(state, hit.y);
        script::PushNumber(state, hit.z);
        if (hit.kind == dt::Kind::Word)
            script::PushString(state, hit.word);
        else
            script::PushNil(state);
        return 10;
    }

    /// TormentWorldToScreen(x, y, z): the point in GetCursorPosition's units, or nil behind the camera or
    /// outside the world view.
    int __cdecl WorldToScreen(void* state)
    {
        void* frame = *reinterpret_cast<void* const*>(sites::kCurrentWorldFrame);
        if (!frame || !*reinterpret_cast<void* const*>(static_cast<char*>(frame) + sites::kWorldFrameCamera) ||
            !script::IsNumber(state, 1) || !script::IsNumber(state, 2) || !script::IsNumber(state, 3))
        {
            script::PushNil(state);
            return 1;
        }
        const float world[3] = {
            static_cast<float>(script::ToNumber(state, 1)),
            static_cast<float>(script::ToNumber(state, 2)),
            static_cast<float>(script::ToNumber(state, 3)),
        };
        float screen[3] = {};
        uint32_t clip = 0;
        if (!wxl::game::Native<sites::GetScreenCoordinatesFn>(sites::kGetScreenCoordinates)(frame, nullptr, world,
                                                                                               screen, &clip))
        {
            script::PushNil(state);
            return 1;
        }
        const float compensation = *reinterpret_cast<const float*>(sites::kAspectCompensation);
        const float widthScale = *reinterpret_cast<const float*>(sites::kDdcWidthScale);
        script::PushNumber(state, dt::CursorUnits(screen[0], compensation, widthScale));
        script::PushNumber(state, dt::CursorUnits(screen[1], compensation, widthScale));
        return 2;
    }

    /// The four damage text hooks; all or none counts, and none of them changes what the engine draws until
    /// the addon reads.
    bool AttachDamageText()
    {
        const struct
        {
            const char* name;
            uintptr_t target;
            void* detour;
            void** original;
        } hooks[] = {
            {"torment.add-world-damage-text", sites::kAddWorldDamageText, reinterpret_cast<void*>(&AddWorldDamageText),
             reinterpret_cast<void**>(&g_addWorldDamageText)},
            {"torment.add-world-text", sites::kAddWorldText, reinterpret_cast<void*>(&AddWorldText),
             reinterpret_cast<void**>(&g_addWorldText)},
            {"torment.add-world-healing-text", sites::kAddWorldHealingText,
             reinterpret_cast<void*>(&AddWorldHealingText), reinterpret_cast<void**>(&g_addWorldHealingText)},
            {"torment.create-world-text", sites::kCreateWorldText, reinterpret_cast<void*>(&CreateWorldText),
             reinterpret_cast<void**>(&g_createWorldText)},
        };
        bool ok = true;
        for (const auto& hook : hooks)
            ok = g_api->HookAttach(hook.name, hook.target, hook.detour, hook.original, WXL_HOOK_DEFAULT_PRIORITY) &&
                 ok;
        return ok;
    }

    /// OnInput: every client window message. Leaves *handled alone, so the client still gets the key.
    void __cdecl OnInput(void*, const void* args)
    {
        const auto* input = static_cast<const ev::InputArgs*>(args);
        g_keys.OnMessage(input->message, input->wparam);
    }

    /// TormentKeyDown(key): true while the key is held, false when not, nil for a name it does not
    /// know. key is a WoW binding name, as GetBindingKey returns it.
    int __cdecl KeyDown(void* state)
    {
        const int vk = torment::VirtualKeyFor(script::IsString(state, 1) ? script::ToString(state, 1) : nullptr);
        if (vk)
            script::PushBoolean(state, g_keys.IsDown(vk));
        else
            script::PushNil(state);
        return 1;
    }

    /// The client refuses a script function outside Wow.exe's code (Script.hpp, kValidateCallbackSeam).
    /// KeyDown and the two damage text functions are let through; every other pointer still goes to the
    /// client's check.
    void __cdecl Validate(uintptr_t function)
    {
        if (function == reinterpret_cast<uintptr_t>(&KeyDown) ||
            (g_damageTextHooked && (function == reinterpret_cast<uintptr_t>(&DamageTextRead) ||
                                    function == reinterpret_cast<uintptr_t>(&WorldToScreen))))
            return;
        g_validate(function);
    }

    /// Puts the global on the script context before the interface files run on it: GlueXML, then
    /// FrameXML, then each addon (Script.hpp, kInterfaceLoadSeam). Registered on every call, because a
    /// UI reload builds a new context and a pointer compare could match a reused address.
    int __cdecl InterfaceLoad(const char* tocPath, const char* addOnName, void* md5Context, void* status)
    {
        if (script::Context())
        {
            script::Register(kKeyDownGlobal, &KeyDown);
            if (g_damageTextHooked)
            {
                script::Register(kDamageTextReadGlobal, &DamageTextRead);
                script::Register(kWorldToScreenGlobal, &WorldToScreen);
            }
            if (!g_registered)
            {
                g_registered = true;
                g_api->Log(WXL_LOG_INFO, "torment", "%s registered", kKeyDownGlobal);
            }
        }
        // A new interface: nothing queued for the old one is drawn, and the engine draws until the addon reads.
        g_hits.Clear();
        g_reader.Reset();
        return g_interfaceLoad(tocPath, addOnName, md5Context, status);
    }

    // The hook API takes the detours as void*: hold them to the client's own signatures here.
    static_assert(std::is_same_v<decltype(&Validate), script::ValidateCallbackFn>);
    static_assert(std::is_same_v<decltype(&InterfaceLoad), script::InterfaceLoadFn>);
    static_assert(std::is_same_v<decltype(&AddWorldDamageText), sites::AddWorldDamageTextFn>);
    static_assert(std::is_same_v<decltype(&AddWorldText), sites::AddWorldTextFn>);
    static_assert(std::is_same_v<decltype(&AddWorldHealingText), sites::AddWorldHealingTextFn>);
    static_assert(std::is_same_v<decltype(&CreateWorldText), sites::CreateWorldTextFn>);
    static_assert(std::is_same_v<decltype(&DamageTextRead), decltype(&KeyDown)>);
    static_assert(std::is_same_v<decltype(&WorldToScreen), decltype(&KeyDown)>);
} // namespace

extern "C" const WXL_PluginInfo* __cdecl WXL_Query(void)
{
    return &kInfo;
}

extern "C" int __cdecl WXL_Load(const WXL_Api* api)
{
    g_api = api;

    // The core's log, Logs\wxl-core.log beside Wow.exe: local only, nothing uploads (D10 A).
    api->Log(WXL_LOG_INFO, "torment", "Torment module loaded (v%u)", kTormentModuleVersion);

    ApplyClassPatches();

    api->Subscribe(static_cast<uint32_t>(ev::Event::OnInput), &OnInput, nullptr);

    // The validator first: a registered global the client then refuses would be a fatal error on the
    // first call. Either attach failing leaves the global absent, and the addon falls back (D6 A).
    if (!api->HookAttach("torment.validate", script::kValidateCallbackSeam, reinterpret_cast<void*>(&Validate),
                         reinterpret_cast<void**>(&g_validate), WXL_HOOK_DEFAULT_PRIORITY) ||
        !api->HookAttach("torment.interface-load", script::kInterfaceLoadSeam, reinterpret_cast<void*>(&InterfaceLoad),
                         reinterpret_cast<void**>(&g_interfaceLoad), WXL_HOOK_DEFAULT_PRIORITY))
    {
        api->Log(WXL_LOG_ERROR, "torment", "hook attach failed; %s stays absent", kKeyDownGlobal);
        return 1;
    }

    // Without every one of them the globals stay absent and the addon falls back; a hook that did attach
    // queues nothing, since the addon never reads.
    g_damageTextHooked = AttachDamageText();
    if (g_damageTextHooked)
        api->Log(WXL_LOG_INFO, "torment", "damage text hooks attached");
    else
        api->Log(WXL_LOG_ERROR, "torment", "damage text hook attach failed; %s and %s stay absent",
                 kDamageTextReadGlobal, kWorldToScreenGlobal);
    return 1;
}
