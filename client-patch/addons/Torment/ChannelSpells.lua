-- The channelled skills the observer in ChannelObserver.lua watches: spell id -> skill name.
-- Hand-kept list; test_channel_spells.py holds it equal to the channel rows of
-- data/generated/spell_value_map.csv (every spell with channel_tick_frames_count, the set the
-- server's WizardChannel reads), so a new channel rune cannot be missing here.
-- Archon's Disintegration Wave (83276) is left off: whether it holds like the others is not ruled.
Diablocraft = Diablocraft or {}
Diablocraft.ChannelSpells = {
    [81004] = "Whirlwind", [81043] = "Whirlwind", [81044] = "Whirlwind",
    [81045] = "Whirlwind", [81046] = "Whirlwind", [81047] = "Whirlwind",
    [83104] = "Ray of Frost", [83146] = "Ray of Frost", [83147] = "Ray of Frost",
    [83148] = "Ray of Frost", [83149] = "Ray of Frost", [83150] = "Ray of Frost",
    [83106] = "Arcane Torrent", [83156] = "Arcane Torrent", [83157] = "Arcane Torrent",
    [83158] = "Arcane Torrent", [83159] = "Arcane Torrent", [83160] = "Arcane Torrent",
    [83107] = "Disintegrate", [83161] = "Disintegrate", [83162] = "Disintegrate",
    [83163] = "Disintegrate", [83164] = "Disintegrate", [83165] = "Disintegrate",
}
