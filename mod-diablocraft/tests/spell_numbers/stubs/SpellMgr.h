/* Test double for the core's spell store (step 3 harness only). */
#ifndef DC_TEST_SPELLMGR_H
#define DC_TEST_SPELLMGR_H

#include "SpellInfo.h"
#include <unordered_map>

class SpellMgr
{
public:
    static SpellMgr* instance()
    {
        static SpellMgr manager;
        return &manager;
    }

    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto found = _store.find(id);
        return found == _store.end() ? nullptr : &found->second;
    }

    SpellInfo& Add(uint32 id)
    {
        SpellInfo& info = _store[id];
        info.Id = id;
        return info;
    }

private:
    std::unordered_map<uint32, SpellInfo> _store;
};

#define sSpellMgr SpellMgr::instance()

#endif
