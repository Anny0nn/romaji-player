"""Bounded, persistent JSON romanizer. Timing and durable storage belong to Rust."""

import hashlib
import importlib.metadata
import json
import re
import sys
import unicodedata
from pathlib import Path

import cutlet
import jaconv
import unidic_lite
from cutlet.cutlet import normalize_text

PROTOCOL = 2
REPRESENTATION = "source-reading-v1"
LIMIT = 65536
IDENTITY = (
    "request_id",
    "track_id",
    "snapshot_id",
    "occurrence_id",
    "override_revision",
)
WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\U00020000-\U0003134f]")
# Song/context readings supported by lyric references and acoustic comparisons.
# SAKURA: https://www.uta-net.com/song/37330/
# departure!: https://www.uta-net.com/song/123698/
# Tabi no Tochuu: https://www.uta-net.com/song/64970/ (ハッカ色);
# conventional color-name reading はっかいろ, corroborated by TIFA alternatives.
SONG_READINGS = {
    "1lTfD2M6UpJRWi3YLb8qb5": [(re.compile(r"君\s*は\s*(故郷)\s*を\s*出\s*た"), "まち")],
    "4cH6RfZ1qIuz6sumRoDEGK": [(re.compile(r"青\s*い\s*(地球)\s*に\s*ありがとう"), "ほし")],
    "6KeWalxT7jDYdNfwiBtBzt": [(re.compile(r"(ハッカ色|薄荷色)\s*の\s*月"), "はっかいろ")],
}


def byte_length(text):
    return len(text.encode("utf-8"))


def slice_bytes(text, span):
    start, end = span
    if not (type(start) is int and type(end) is int):
        raise TypeError("invalid_span")
    data = text.encode("utf-8")
    if not 0 <= start < end <= len(data):
        raise ValueError("invalid_span")
    return data[start:end].decode("utf-8", errors="strict")


def katakana(text):
    """Change script only; preserve ASCII, punctuation and unavailable readings."""
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" or ch in "ゝゞ" else ch for ch in text)


def alignment_spelling(text):
    """Remove punctuation without turning an English contraction into another word."""
    return "".join(
        char
        for i, char in enumerate(text)
        if char.isalnum()
        or (
            char == "'"
            and 0 < i < len(text) - 1
            and all(c.isascii() and c.isalpha() for c in (text[i - 1], text[i + 1]))
        )
    )


def boundary_map(raw, normalized):
    """Only independently reconstructible boundaries are exact. Never round."""
    associations = []
    for index in range(len(raw) + 1):
        left = normalize_text(raw[:index])
        right = normalize_text(raw[index:])
        if left + right == normalized:
            associations.append([byte_length(raw[:index]), byte_length(left)])
    return associations


class Converter:
    def __init__(self):
        self.cut = cutlet.Cutlet()
        self.cut.use_foreign_spelling = False
        self.cut.use_wo = False
        self.cut.ensure_ascii = False
        versions = {
            name: importlib.metadata.version(name)
            for name in ("cutlet", "fugashi", "unidic-lite", "mojimoji", "jaconv")
        }
        digest = hashlib.sha256()
        dictionary = Path(unidic_lite.DICDIR)
        for name in ("sys.dic", "unk.dic", "char.bin", "matrix.bin", "dicrc"):
            with (dictionary / name).open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        signature = {
            "protocol": PROTOCOL,
            "representation": REPRESENTATION,
            "versions": versions,
            "python": sys.version,
            "unicode": unicodedata.unidata_version,
            "dictionary_sha256": digest.hexdigest(),
            "transform_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "settings": {"foreign": False, "wo": False, "ascii": False},
        }
        self.signature = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()

    def convert(self, request):
        if request.get("protocol_version") != PROTOCOL:
            raise ValueError("unsupported_protocol")
        if request.get("command") == "hello":
            return {
                "protocol_version": PROTOCOL,
                "request_id": request["request_id"],
                "conversion_signature": self.signature,
            }
        if request.get("expected_conversion_signature") != self.signature:
            raise ValueError("signature_mismatch")
        raw = request["raw_line"]
        if not isinstance(raw, str) or byte_length(raw) > 8192 or "\n" in raw:
            raise ValueError("invalid_line")
        normalized = normalize_text(raw)
        boundaries = boundary_map(raw, normalized)
        reverse = {}
        for raw_byte, norm_byte in boundaries:
            reverse.setdefault(norm_byte, []).append(raw_byte)

        def raw_span(span):
            left = reverse.get(span[0], [])
            right = reverse.get(span[1], [])
            return [left[0], right[0]] if len(left) == len(right) == 1 else None

        words = []
        if not JAPANESE.search(raw):
            # Preserve spaces/punctuation of entirely non-Japanese lines exactly.
            romaji = raw
            for match in WORD.finditer(raw):
                span = [byte_length(raw[: match.start()]), byte_length(raw[: match.end()])]
                words.append(self.word(raw, span, None, span, []))
                words[-1]["hiragana"] = slice_bytes(raw, span)
        else:
            nodes = self.cut.tagger(normalized)
            tokens = self.cut.romaji_tokens(nodes, capitalize=False)
            # Empty pronunciation tokens (for example leading wave dashes) can
            # introduce whitespace that Cutlet's whole-string API strips.
            if "".join(map(str, tokens)).strip() != self.cut.romaji(raw, capitalize=False):
                raise ValueError("assembly_mismatch")
            crossing = set()
            for index in range(1, len(nodes)):
                if (
                    self.cut.romaji_word(nodes[index - 1]).endswith("っ")
                    and tokens[index - 1].space
                    and tokens[index].surface
                ):
                    # Cutlet transfers the next token's first consonant to a
                    # trailing っ, but can leave a space inside that syllable.
                    # Contiguous Japanese nodes belong to one pronunciation
                    # group: retain both source spans and join their display.
                    # Explicit source whitespace remains ambiguous, so keep
                    # the conservative unresolved mapping for that case.
                    if (
                        not nodes[index].white_space
                        and JAPANESE.search(nodes[index - 1].surface)
                        and JAPANESE.search(nodes[index].surface)
                        and WORD.fullmatch(tokens[index - 1].surface)
                        and WORD.fullmatch(tokens[index].surface)
                    ):
                        tokens[index - 1].space = False
                    else:
                        crossing.update((index - 1, index))
            crossing_spans = set()
            source_readings = set()
            assembled, positions, readings, pronunciations = "", [], {}, {}
            cursor = 0
            for index, (node, token) in enumerate(zip(nodes, tokens, strict=True)):
                cursor += node.rlength
                norm_span = [cursor - node.length, cursor]
                if index in crossing:
                    crossing_spans.add(tuple(norm_span))
                output_span = [byte_length(assembled), byte_length(assembled + token.surface)]
                assembled += str(token)
                parts = (
                    self.dotted_kana_parts(node.surface, token.surface, norm_span, output_span)
                    if node.is_unk and index not in crossing
                    else []
                )
                if parts:
                    for norm_part, output_part, kana in parts:
                        positions.append((norm_part, output_part))
                        readings[tuple(norm_part)] = kana
                        source_readings.add(tuple(norm_part))
                        pronunciations[tuple(norm_part)] = None
                    continue
                positions.append((norm_span, output_span))
                reading = node.feature.kana if not node.is_unk else node.surface
                if not reading:
                    reading = node.surface
                kana = jaconv.kata2hira(reading)
                readings[tuple(norm_span)] = (
                    None if re.search(r"[\u3400-\u9fff\U00020000-\U0003134f]", kana) else kana
                )
                pronunciations[tuple(norm_span)] = (
                    jaconv.kata2hira(node.feature.pron)
                    if not node.is_unk and node.feature.pron
                    else None
                )
            romaji = assembled.rstrip()
            for match in WORD.finditer(romaji):
                output = [byte_length(romaji[: match.start()]), byte_length(romaji[: match.end()])]
                constituents = [
                    (norm, out)
                    for norm, out in positions
                    if out[0] < output[1] and out[1] > output[0]
                ]
                if not constituents:
                    raise ValueError("missing_node")
                norm = [constituents[0][0][0], constituents[-1][0][1]]
                complete = all(
                    output[0] <= out[0] and out[1] <= output[1] for _, out in constituents
                )
                crossed = any(tuple(n) in crossing_spans for n, _ in constituents)
                source = raw_span(norm) if complete and not crossed else None
                word = self.word(raw, source, norm, output, [n for n, _ in constituents])
                pieces = [readings[tuple(n)] for n, _ in constituents]
                word["hiragana"] = (
                    "".join(pieces) if complete and all(p is not None for p in pieces) else None
                )
                spoken = [pronunciations[tuple(n)] for n, _ in constituents]
                word["pronunciation"] = "".join(spoken) if complete and all(spoken) else None
                word["reading_origin"] = (
                    "source"
                    if all(tuple(n) in source_readings for n, _ in constituents)
                    else "dictionary"
                )
                if crossed:
                    word["mapping_reason"] = "cross_word_gemination"
                words.append(word)

        def source_envelope(word):
            """Conservative complete source group for an explicitly repaired mapping."""
            if word["raw_span"] is not None:
                return word["raw_span"]
            norm = word["normalized_span"]
            if norm is None:
                return None
            left = [raw for raw, at in boundaries if at <= norm[0]]
            right = [raw for raw, at in boundaries if at >= norm[1]]
            return [max(left), min(right)] if left and right else None

        applied, pending, accepted = [], [], []
        for override in request.get("overrides", []):
            record = override["id"]
            span = override.get("raw_span")
            try:
                if slice_bytes(raw, span) != override["expected_text"]:
                    raise ValueError("changed_text")
                replacement = override["replacement"].strip()
                if "\n" in replacement or "\r" in replacement or not WORD.search(replacement):
                    raise ValueError("invalid_reading")
                mapping = override["kind"] in ("mapping", "mapping_kana")
                envelopes = [(w, source_envelope(w) if mapping else w["raw_span"]) for w in words]
                intersecting = [
                    (w, source)
                    for w, source in envelopes
                    if source is not None and source[0] < span[1] and span[0] < source[1]
                ]
                candidates = [w for w, source in intersecting]
                if (
                    not candidates
                    or intersecting[0][1][0] != span[0]
                    or intersecting[-1][1][1] != span[1]
                    or any(
                        not (span[0] <= source[0] < source[1] <= span[1])
                        for _, source in intersecting
                    )
                ):
                    raise ValueError("unmapped_span")
                if override["kind"] in ("reading", "reading_kana") and len(candidates) != 1:
                    raise ValueError("changed_grouping")
                if override["kind"] not in ("reading", "mapping", "reading_kana", "mapping_kana"):
                    raise ValueError("invalid_kind")
                explicit_kana = override.get("hiragana")
                if override["kind"].endswith("_kana"):
                    if not isinstance(explicit_kana, str) or not re.fullmatch(
                        r"[ぁ-ゖー]+(?: [ぁ-ゖー]+)*", explicit_kana
                    ):
                        raise ValueError("invalid_kana")
                    if self.kana_romaji(explicit_kana) != replacement:
                        raise ValueError("inconsistent_kana_romaji")
                if any(span[0] < other[1] and span[1] > other[0] for other in accepted):
                    raise ValueError("conflicting_override")
                accepted.append(span)
                applied.append(record)
                candidates[0]["replacement"] = replacement
                candidates[0]["hiragana"] = (
                    explicit_kana or self.corrected_hiragana(replacement)
                    if JAPANESE.search(override["expected_text"])
                    else replacement
                )
                candidates[0]["override_id"] = record
                candidates[0]["pronunciation"] = None
                candidates[0]["reading_origin"] = "saved"
                candidates[0]["raw_span"] = span
                candidates[0]["expected_text"] = override["expected_text"]
                candidates[0]["mapping_status"] = "mapped"
                candidates[0]["mapping_reason"] = None
                candidates[0]["output_span"][1] = candidates[-1]["output_span"][1]
                candidates[0]["normalized_span"] = None
                candidates[0]["constituent_nodes"] = []
                for word in candidates[1:]:
                    words.remove(word)
            except (ValueError, KeyError, TypeError, UnicodeError):
                pending.append({"id": record, "reason": "invalid_or_unmapped_override"})

        for pattern, kana in SONG_READINGS.get(request["track_id"], []):
            for match in pattern.finditer(raw):
                source = [byte_length(raw[: match.start(1)]), byte_length(raw[: match.end(1)])]
                for word in words:
                    if word["raw_span"] == source and word["override_id"] is None:
                        # Each default names one source word. MeCab may split kana
                        # internally (はっかいろ -> "hak kairo"); keep its romaji atomic.
                        word["replacement"] = self.cut.romaji(kana, capitalize=False).replace(
                            " ", ""
                        )
                        word["hiragana"] = kana
                        word["pronunciation"] = None
                        word["reading_origin"] = "song"

        output, cursor = "", 0
        data = romaji.encode("utf-8")
        for word in words:
            start, end = word["output_span"]
            output += data[cursor:start].decode()
            text = word.pop("replacement", data[start:end].decode())
            word["output_span"] = [byte_length(output), byte_length(output + text)]
            output += text
            cursor = end
        output += data[cursor:].decode()
        hiragana, kata, cursor = "", "", 0
        data = output.encode("utf-8")
        for word in words:
            start, end = word["output_span"]
            hiragana += data[cursor:start].decode()
            kata += katakana(data[cursor:start].decode())
            written = word.pop("hiragana", None)
            reading = written or "？"
            word["hiragana_span"] = [byte_length(hiragana), byte_length(hiragana + reading)]
            hiragana += reading
            rendered_kata = katakana(reading)
            word["katakana_span"] = [byte_length(kata), byte_length(kata + rendered_kata)]
            kata += rendered_kata
            source = word["expected_text"] or ""
            spoken = word.pop("pronunciation", None)
            origin = word.pop("reading_origin", "source")
            if spoken and not re.fullmatch(r"[ぁ-ゖー]+(?: [ぁ-ゖー]+)*", spoken):
                spoken = None
            word["reading"] = {
                "written": written,
                "romaji": slice_bytes(output, word["output_span"]),
                "alignment_text": alignment_spelling(
                    source if not written or "？" in written else written
                ),
                "pronunciation": spoken if written else None,
                "origin": origin if written else "unavailable",
            }
            cursor = end
        hiragana += data[cursor:].decode()
        kata += katakana(data[cursor:].decode())
        response = {
            "protocol_version": PROTOCOL,
            **{key: request[key] for key in IDENTITY},
            "conversion_signature": self.signature,
            "normalized_line": normalized,
            "romaji": output,
            "hiragana": hiragana,
            "katakana": kata,
            "representation": REPRESENTATION,
            "words": words,
            "boundary_associations": boundaries,
            "applied_override_ids": applied,
            "pending_overrides": pending,
        }
        if request.get("command") == "candidates":
            response["reading_candidates"] = self.reading_candidates(raw, normalized, words)
        if request.get("command") == "canonical":
            if not re.fullmatch(r"[ぁ-ゖー]+(?: [ぁ-ゖー]+)*", raw):
                raise ValueError("invalid_canonical_kana")
            response["canonical_reading"] = {"hiragana": raw, "romaji": self.kana_romaji(raw)}
        return response

    def kana_romaji(self, kana):
        # Spaces in a correction are deliberate display boundaries. Dictionary
        # token boundaries inside each kana part are not boundaries of its source word.
        return " ".join(
            self.cut.romaji(part, capitalize=False).replace(" ", "") for part in kana.split()
        )

    def dotted_kana_parts(self, surface, output, normalized, rendered):
        """Prove an ordered subnode bijection; never guess from partial romanization."""
        if not re.fullmatch(r"[ぁ-ゖァ-ヶー]+(?:・[ぁ-ゖァ-ヶー]+)+", surface):
            return []
        pieces = surface.split("・")
        kana = [jaconv.kata2hira(piece) for piece in pieces]
        romanized = [self.cut.map_kana(piece) for piece in kana]
        if (
            "/".join(romanized) != output
            or any(not WORD.fullmatch(piece) for piece in romanized)
            or normalized[1] - normalized[0] != byte_length(surface)
            or rendered[1] - rendered[0] != byte_length(output)
        ):
            return []
        result = []
        source_at, output_at = normalized[0], rendered[0]
        for piece, reading, romaji in zip(pieces, kana, romanized, strict=True):
            source_end = source_at + byte_length(piece)
            output_end = output_at + byte_length(romaji)
            result.append(([source_at, source_end], [output_at, output_end], reading))
            source_at = source_end + byte_length("・")
            output_at = output_end + byte_length("/")
        return result

    def reading_candidates(self, raw, normalized, words):
        """Bounded alternatives; never select one without independent singing evidence."""
        paths = []
        for nodes in self.cut.tagger.nbestToNodeList(normalized, 32):
            cursor, path = 0, []
            for node in nodes:
                cursor += node.rlength
                path.append(([cursor - node.length, cursor], node.feature.kana or node.surface))
            paths.append(path)
        groups, budget = [], 192
        for word in words:
            source = word["raw_span"]
            if source is None or word["override_id"] is not None or budget <= 0:
                continue
            surface = slice_bytes(raw, source)
            if not re.search(r"[\u3400-\u9fff\U00020000-\U0003134f]", surface):
                continue
            readings = []
            norm = word["normalized_span"]
            for path in paths:
                pieces = [(s, k) for s, k in path if norm and s[0] < norm[1] and s[1] > norm[0]]
                if pieces and pieces[0][0][0] == norm[0] and pieces[-1][0][1] == norm[1]:
                    readings.append("".join(k for _, k in pieces))
            # Contextual paths can be dominated by ambiguity elsewhere in a line.
            # Add bounded paths for this exact inflected envelope, never a lemma.
            readings.extend(
                "".join(node.feature.kana or node.surface for node in nodes)
                for nodes in self.cut.tagger.nbestToNodeList(surface, 32)
            )
            candidates = []
            for reading in readings:
                kana = jaconv.kata2hira(reading)
                if not re.fullmatch(r"[ぁ-ゖー]{1,128}", kana) or any(
                    c["hiragana"] == kana for c in candidates
                ):
                    continue
                candidates.append({"hiragana": kana, "romaji": self.kana_romaji(kana)})
                if len(candidates) >= min(16, budget):
                    break
            if len(candidates) > 1:
                groups.append(
                    {"raw_span": source, "expected_text": surface, "candidates": candidates}
                )
                budget -= len(candidates)
        return groups

    def corrected_hiragana(self, replacement):
        # Existing romaji overrides have no kana field. Accept a reverse conversion
        # only when the same romanizer reconstructs it; never guess English as kana.
        prepared = re.sub(r"nn(?=[aiueo])", "n'n", replacement.lower())
        kana = jaconv.alphabet2kana(prepared)
        canonical = lambda text: re.sub(r"[\s']", "", text.lower())
        return (
            kana
            if canonical(self.cut.romaji(kana, capitalize=False)) == canonical(replacement)
            else None
        )

    @staticmethod
    def word(raw, source, normalized, output, nodes):
        return {
            "raw_span": source,
            "normalized_span": normalized,
            "output_span": output,
            "expected_text": slice_bytes(raw, source) if source else None,
            "constituent_nodes": nodes,
            "override_id": None,
            "mapping_status": "mapped" if source else "needs_review",
            "mapping_reason": None if source else "non_bijective_or_partial_node",
        }


def main():
    converter = Converter()
    while line := sys.stdin.buffer.readline(LIMIT + 1):
        if len(line) > LIMIT:
            break
        request = {}
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                request = {}
                raise TypeError("invalid_request")
            response = converter.convert(request)
        except (ValueError, KeyError, TypeError, UnicodeError):
            # Never echo complete lyrics or exception strings into diagnostic output.
            response = {
                "protocol_version": PROTOCOL,
                "request_id": request.get("request_id"),
                "error": "invalid_request",
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
