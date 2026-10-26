// The queue behind TormentDamageTextRead (docs/contracts/damage-text.md): the hits the engine would draw a
// floating number or word for, held until the addon reads them, and whether the addon is reading at all.
// Plain logic with no client calls, so client-extension/tests/damage_text_test.cpp runs it on the CI runner.

#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace torment::damage_text
{
    enum class Kind : uint8_t
    {
        Damage,
        Heal,
        Word,
    };

    /// One hit, as TormentDamageTextRead hands it over.
    struct Hit
    {
        Kind kind = Kind::Damage;
        uint32_t amount = 0;
        uint32_t school = 0;
        bool crit = false;
        bool periodic = false;
        bool own = false;
        float x = 0.0f;
        float y = 0.0f;
        float z = 0.0f;
        /// The engine's word for a Kind::Word, NUL terminated; empty otherwise. The engine's own text
        /// buffer is this size (WORLDTEXTSTRING::m_text).
        char word[64] = {};

        void SetWord(const char* text)
        {
            word[0] = '\0';
            if (text)
            {
                std::strncpy(word, text, sizeof word - 1);
                word[sizeof word - 1] = '\0';
            }
        }
    };

    /// The school mask of a hit that carries no spell: a white melee swing, a damage-shield hit.
    constexpr uint32_t kNoSpellSchool = 1;

    /// How long after the addon's last read it still counts as reading. ponytail: one frame at 2 fps; a
    /// longer stall hands the next hits back to the engine, which then draws them as it always did.
    constexpr uint32_t kReadingWindowMs = 500;

    /// The oldest hit first; when full, a new hit drops the oldest.
    class Queue
    {
    public:
        /// ponytail: a ceiling, so a reader that stops cannot grow it; the oldest hit is the stalest.
        static constexpr size_t kCapacity = 128;

        void Push(const Hit& hit)
        {
            if (count_ == kCapacity)
            {
                head_ = (head_ + 1) % kCapacity;
                --count_;
            }
            hits_[(head_ + count_) % kCapacity] = hit;
            ++count_;
        }

        bool Pop(Hit& out)
        {
            if (!count_)
                return false;
            out = hits_[head_];
            head_ = (head_ + 1) % kCapacity;
            --count_;
            return true;
        }

        void Clear()
        {
            head_ = 0;
            count_ = 0;
        }

        size_t Size() const
        {
            return count_;
        }

    private:
        Hit hits_[kCapacity];
        size_t head_ = 0;
        size_t count_ = 0;
    };

    /// Whether the addon is drawing the numbers: it read within kReadingWindowMs. Times are the client's
    /// millisecond tick count, which wraps; the difference is taken unsigned, so a wrap reads as a short gap.
    class Reader
    {
    public:
        void MarkRead(uint32_t nowMs)
        {
            lastReadMs_ = nowMs;
            hasRead_ = true;
        }

        bool Reading(uint32_t nowMs) const
        {
            return hasRead_ && nowMs - lastReadMs_ <= kReadingWindowMs;
        }

        /// A new interface: the engine draws until the addon's first read on it.
        void Reset()
        {
            hasRead_ = false;
        }

    private:
        uint32_t lastReadMs_ = 0;
        bool hasRead_ = false;
    };

    /// A device (DDC) coordinate in GetCursorPosition's units, by the client's own formula
    /// (Script_GetCursorPosition: DDCToNDCWidth(aspect compensation * 1024 * ddc), for both axes).
    inline float CursorUnits(float ddc, float aspectCompensation, float ddcWidthScale)
    {
        return aspectCompensation * 1024.0f * ddc / ddcWidthScale;
    }
} // namespace torment::damage_text
