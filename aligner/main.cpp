// One model load, bounded crops, explicit Japanese word units. No lyric logs.
#include "forced_aligner.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static uint32_t read_u32(std::istream &in) {
    unsigned char bytes[4]{};
    if (!in.read(reinterpret_cast<char *>(bytes), 4)) throw std::runtime_error("truncated input");
    return uint32_t(bytes[0]) | uint32_t(bytes[1]) << 8 | uint32_t(bytes[2]) << 16 | uint32_t(bytes[3]) << 24;
}

static std::string quoted(const std::string &value) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char ch : value) {
        if (ch == '"' || ch == '\\') { out += '\\'; out += char(ch); }
        else if (ch < 32) { out += "\\u00"; out += hex[ch >> 4]; out += hex[ch & 15]; }
        else out += char(ch);
    }
    return out + '"';
}

struct Word { uint32_t start; uint32_t end; std::string text; };
struct Crop { uint32_t occurrence; uint32_t start; uint32_t end; std::vector<Word> words; };

static std::vector<Crop> read_crops(std::istream &in, uint32_t samples) {
    if (read_u32(in) != 2) throw std::runtime_error("unsupported protocol");
    const auto count = read_u32(in);
    if (count > 2000) throw std::runtime_error("too many lines");
    std::vector<Crop> crops;
    for (uint32_t i = 0; i < count; ++i) {
        Crop crop{read_u32(in), read_u32(in), read_u32(in), {}};
        const auto word_count = read_u32(in);
        if (!word_count || word_count > 4096 || crop.start >= crop.end || crop.end > samples || crop.end - crop.start > 16000 * 30)
            throw std::runtime_error("invalid lyric crop");
        uint32_t previous_end = 0, total_bytes = 0;
        for (uint32_t word_index = 0; word_index < word_count; ++word_index) {
            Word word{read_u32(in), read_u32(in), {}};
            const auto length = read_u32(in);
            if (!length || length > 8192 || total_bytes + length > 8192 || word.start < previous_end || word.start >= word.end || word.end > 8192)
                throw std::runtime_error("invalid word span");
            word.text.resize(length);
            if (!in.read(word.text.data(), length)) throw std::runtime_error("truncated word");
            if (word.text.find_first_of(" \t\r\n") != std::string::npos) throw std::runtime_error("word contains separator");
            total_bytes += length;
            previous_end = word.end;
            crop.words.push_back(std::move(word));
        }
        crops.push_back(std::move(crop));
    }
    if (in.peek() != std::char_traits<char>::eof()) throw std::runtime_error("extra request bytes");
    return crops;
}

static void self_test() {
    if (quoted("a\"\n\\") != "\"a\\\"\\u000a\\\\\"") throw std::runtime_error("JSON escaping");
    for (const std::string &bytes : {std::string{}, std::string(4, '\0')}) {
        std::istringstream in(bytes);
        bool rejected = false;
        try { (void)read_crops(in, 16000); } catch (const std::exception &) { rejected = true; }
        if (!rejected) throw std::runtime_error("malformed request accepted");
    }
    const auto fixture = [](uint32_t start, uint32_t end, const std::string &text) {
        std::string out;
        const auto append = [&out](uint32_t value) {
            for (int shift = 0; shift < 32; shift += 8) out += char((value >> shift) & 255);
        };
        for (uint32_t value : {2u, 1u, 4u, 0u, 8000u, 1u, start, end, uint32_t(text.size())}) append(value);
        return out + text;
    };
    std::istringstream valid(fixture(0, 3, "さくら"));
    const auto parsed = read_crops(valid, 16000);
    if (parsed.size() != 1 || parsed[0].words.size() != 1 || parsed[0].words[0].text != "さくら" || parsed[0].words[0].end != 3)
        throw std::runtime_error("word protocol round trip");
    for (const auto &bytes : {fixture(3, 3, "さくら"), fixture(0, 8193, "さくら"), fixture(0, 3, "a b"), fixture(0, 3, "")}) {
        std::istringstream in(bytes);
        bool rejected = false;
        try { (void)read_crops(in, 16000); } catch (const std::exception &) { rejected = true; }
        if (!rejected) throw std::runtime_error("malformed word accepted");
    }
    std::cout << "{\"protocol\":2,\"self_test\":true}\n";
}

int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--self-test") { self_test(); return 0; }
        if (argc != 4) throw std::runtime_error("expected model, mono PCM and crop request");
        std::ifstream pcm(argv[2], std::ios::binary | std::ios::ate);
        const auto bytes = pcm.tellg();
        if (bytes <= 0 || bytes > 16000 * 4 * 600 || bytes % 4 != 0) throw std::runtime_error("invalid PCM size");
        pcm.seekg(0);
        std::vector<float> samples(static_cast<size_t>(bytes) / 4);
        if (!pcm.read(reinterpret_cast<char *>(samples.data()), bytes) ||
            std::any_of(samples.begin(), samples.end(), [](float x) { return !std::isfinite(x); }))
            throw std::runtime_error("invalid PCM samples");
        std::ifstream request(argv[3], std::ios::binary);
        const auto crops = read_crops(request, uint32_t(samples.size()));
        qwen3_asr::ForcedAligner aligner;
        if (!aligner.load_model(argv[1])) throw std::runtime_error("model could not load");
        aligner.set_n_threads(4);
        for (const auto &crop : crops) {
            // Silence is a negative control, not an invitation to place the text.
            double energy = 0;
            for (auto i = crop.start; i < crop.end; ++i) energy += double(samples[i]) * samples[i];
            if (energy / (crop.end - crop.start) < 1e-8) {
                std::cout << "{\"occurrence\":" << crop.occurrence << ",\"units\":[]}\n" << std::flush;
                continue;
            }
            std::string transcript;
            for (const auto &word : crop.words) {
                if (!transcript.empty()) transcript += ' ';
                transcript += word.text;
            }
            // This argument selects segmentation, not the acoustic language.
            // Rust supplies Japanese word groups; avoid re-splitting them into characters.
            const auto result = aligner.align(samples.data() + crop.start, crop.end - crop.start, transcript, "presegmented");
            std::cout << "{\"occurrence\":" << crop.occurrence << ",\"units\":[";
            if (result.success && result.words.size() == crop.words.size()) for (size_t i = 0; i < result.words.size(); ++i) {
                const auto &word = result.words[i];
                if (i) std::cout << ',';
                std::cout << "{\"raw_span\":[" << crop.words[i].start << ',' << crop.words[i].end << "],\"text\":" << quoted(word.word) << ",\"start_ms\":" << std::lround(word.start * 1000)
                          << ",\"end_ms\":" << std::lround(word.end * 1000) << '}';
            }
            std::cout << "]}\n" << std::flush;
        }
        return 0;
    } catch (const std::exception &) {
        std::cerr << "Local alignment failed; audio and lyric contents were not logged.\n";
        return 1;
    }
}
