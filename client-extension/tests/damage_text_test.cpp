// Unit test of the queue behind TormentDamageTextRead (client-extension/torment/DamageText.hpp,
// docs/contracts/damage-text.md). Built and run by the client-extension CI job on windows-latest, outside
// the module so it never lands in Torment.dll. Exit code is the number of failed checks.

#include "DamageText.hpp"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace
{
    int g_failed = 0;

    void Check(bool ok, const char* what)
    {
        if (!ok)
        {
            std::printf("FAIL: %s\n", what);
            ++g_failed;
        }
    }

    torment::damage_text::Hit HitOf(uint32_t amount)
    {
        torment::damage_text::Hit hit;
        hit.amount = amount;
        return hit;
    }
} // namespace

int main()
{
    namespace dt = torment::damage_text;

    {
        dt::Queue queue;
        dt::Hit out;
        Check(!queue.Pop(out), "a new queue is empty");
        queue.Push(HitOf(1));
        queue.Push(HitOf(2));
        Check(queue.Size() == 2, "two pushes hold two hits");
        Check(queue.Pop(out) && out.amount == 1, "the oldest hit comes out first");
        Check(queue.Pop(out) && out.amount == 2, "then the next");
        Check(!queue.Pop(out), "and then the queue is empty");
    }
    {
        dt::Queue queue;
        for (uint32_t i = 0; i < dt::Queue::kCapacity + 3; ++i)
            queue.Push(HitOf(i));
        Check(queue.Size() == dt::Queue::kCapacity, "a full queue holds its capacity");
        dt::Hit out;
        Check(queue.Pop(out) && out.amount == 3, "pushing past full drops the oldest hits");
        uint32_t last = 0;
        while (queue.Pop(out))
            last = out.amount;
        Check(last == dt::Queue::kCapacity + 2, "the newest hit is kept");
    }
    {
        dt::Queue queue;
        queue.Push(HitOf(7));
        queue.Clear();
        dt::Hit out;
        Check(!queue.Pop(out), "a cleared queue is empty");
        queue.Push(HitOf(8));
        Check(queue.Pop(out) && out.amount == 8, "a cleared queue takes new hits");
    }
    {
        dt::Hit hit;
        hit.SetWord("Dodge");
        Check(std::strcmp(hit.word, "Dodge") == 0, "a word is copied");
        char longWord[100];
        std::memset(longWord, 'x', sizeof longWord - 1);
        longWord[sizeof longWord - 1] = '\0';
        hit.SetWord(longWord);
        Check(std::strlen(hit.word) == sizeof hit.word - 1, "a word longer than the engine's buffer is cut to it");
        hit.SetWord(nullptr);
        Check(hit.word[0] == '\0', "no text is an empty word");
    }
    {
        dt::Reader reader;
        Check(!reader.Reading(1000), "the addon is not reading before its first read");
        reader.MarkRead(1000);
        Check(reader.Reading(1000), "a read now counts as reading");
        Check(reader.Reading(1000 + dt::kReadingWindowMs), "a read at the window's edge still counts");
        Check(!reader.Reading(1000 + dt::kReadingWindowMs + 1), "a read past the window does not");
        reader.MarkRead(0xFFFFFF00u);
        Check(reader.Reading(0x10u), "the tick count wrapping reads as a short gap");
        reader.Reset();
        Check(!reader.Reading(0x10u), "a new interface is not reading until its first read");
    }
    {
        // Script_GetCursorPosition at 16:9: compensation 16/9 * 0.75, width scale 16/9 / sqrt((16/9)^2 + 1).
        const float aspect = 16.0f / 9.0f;
        const float compensation = aspect * 0.75f;
        const float widthScale = aspect / std::sqrt(aspect * aspect + 1.0f);
        const float heightScale = 1.0f / std::sqrt(aspect * aspect + 1.0f);
        Check(std::fabs(dt::CursorUnits(heightScale, compensation, widthScale) - 768.0f) < 0.01f,
              "the top of the screen is 768 units up");
        Check(std::fabs(dt::CursorUnits(widthScale, compensation, widthScale) - 768.0f * aspect) < 0.01f,
              "the right of the screen is 768 x aspect units across");
        Check(dt::CursorUnits(0.0f, compensation, widthScale) == 0.0f, "the bottom left is 0");
    }

    if (g_failed)
        std::printf("%d check(s) failed\n", g_failed);
    else
        std::printf("damage_text_test: all checks passed\n");
    return g_failed;
}
