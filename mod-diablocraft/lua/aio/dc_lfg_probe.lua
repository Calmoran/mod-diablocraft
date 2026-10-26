-- luacheck: globals RegisterPacketEvent PrintError
-- Dungeon Finder probe, server half: step (a) of docs/research/lfg-takeover.md 10.5.
--
-- A readout, not a feature: when a GM's client sends CMSG_LFG_JOIN, the GM is told in chat (and the
-- server log gets the same line) exactly which LFGDungeons rows the packet named, before the core
-- handles it. The core then runs its join, which dc_world.cpp:648 still vetoes for everyone, so the
-- line is the only trace the join leaves. It answers the research's section 8 item 2: does the
-- client send a hidden row (type 1, Group_Id 0) that is in no list?
--
-- This file never calls AIO.AddAddon(), so nothing here is sent to a client. ALE hands the hook a
-- copy of the packet (PacketHooks.cpp), so reading it here does not move the core's read position.
local CMSG_LFG_JOIN = 0x35C              -- Opcodes.h:890
local PACKET_EVENT_ON_PACKET_RECEIVE = 5 -- mod-ale Hooks.h:97
local TYPE_SHIFT = 0x1000000             -- a slot is the row id plus its type << 24 (LFGHandler.cpp:66)

RegisterPacketEvent(CMSG_LFG_JOIN, PACKET_EVENT_ON_PACKET_RECEIVE, function(_, packet, player)
    if not player or player:GetGMRank() < 1 then return end
    -- WorldPackets::LFG::LFGJoin::Read: roles, two flags, then the slots
    local roles = packet:ReadULong()
    packet:ReadUByte()
    packet:ReadUByte()
    local slots = {}
    for _ = 1, packet:ReadUByte() do
        local slot = packet:ReadULong()
        slots[#slots + 1] = ("%d (type %d)"):format(slot % TYPE_SHIFT, math.floor(slot / TYPE_SHIFT))
    end
    local line = ("[LFG probe] %s sent CMSG_LFG_JOIN: roles %d, %d row(s): %s")
        :format(player:GetName(), roles, #slots, #slots > 0 and table.concat(slots, ", ") or "none")
    player:SendBroadcastMessage(line)
    -- print() is dropped at the Logger.ALE level the servers run; PrintError shows (dc_version.lua).
    PrintError(line)
end)
