"""Check the relocatable ARM64 helper with no developer environment."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    source = Path("dist/RomajiRomanizer").resolve()
    with tempfile.TemporaryDirectory(prefix="romaji package with spaces ") as scratch:
        moved = Path(scratch) / "RomajiRomanizer"
        # Framework symlinks are sealed resources and must survive distribution.
        shutil.copytree(source, moved, symlinks=True)
        exe = moved / "RomajiRomanizer"
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(moved)],
            check=True,
        )
        architecture = subprocess.run(
            ["/usr/bin/file", str(exe)], capture_output=True, text=True, check=True
        )
        assert "arm64" in architecture.stdout

        def run(inputs):
            return subprocess.run(
                [str(exe)],
                input="\n".join(json.dumps(value) for value in inputs) + "\n",
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                env={"PATH": "/usr/bin:/bin"},
                cwd=scratch,
            )

        hello = {"protocol_version": 1, "request_id": 0, "command": "hello"}
        signature = json.loads(run([hello]).stdout)["conversion_signature"]
        request = {
            "protocol_version": 1,
            "request_id": 1,
            "track_id": "synthetic",
            "snapshot_id": "fixture",
            "occurrence_id": 0,
            "override_revision": 0,
            "expected_conversion_signature": signature,
            "raw_line": "ｶﾞ 食べた を",
            "overrides": [],
        }
        sung_reading = {
            **request,
            "request_id": 2,
            "track_id": "1lTfD2M6UpJRWi3YLb8qb5",
            "raw_line": "君は故郷を出た",
        }
        departure = {
            **request,
            "request_id": 3,
            "track_id": "4cH6RfZ1qIuz6sumRoDEGK",
            "raw_line": "青い地球にありがとう",
        }
        tabi = {
            **request,
            "request_id": 4,
            "track_id": "6KeWalxT7jDYdNfwiBtBzt",
            "raw_line": "ハッカ色の月",
        }
        geminated = {**request, "request_id": 5, "raw_line": "桜ぱっと飛ぶ"}
        process = run([hello, request, sung_reading, departure, tabi, geminated])
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        assert not process.stderr and len(responses) == 6
        assert responses[1]["romaji"] == "ga tabeta o"
        assert responses[1]["hiragana"] == "が たべた を"
        assert [word["raw_span"] for word in responses[1]["words"]] == [
            [0, 6],
            [7, 16],
            [17, 20],
        ]
        song = responses[2]
        word = next(word for word in song["words"] if word["raw_span"] == [6, 12])
        assert word["expected_text"] == "故郷"
        start, end = word["output_span"]
        assert song["romaji"].encode()[start:end].decode() == "machi"
        start, end = word["hiragana_span"]
        assert song["hiragana"].encode()[start:end].decode() == "まち"
        song = responses[3]
        word = next(word for word in song["words"] if word["raw_span"] == [6, 12])
        assert word["expected_text"] == "地球"
        start, end = word["output_span"]
        assert song["romaji"].encode()[start:end].decode() == "hoshi"
        start, end = word["hiragana_span"]
        assert song["hiragana"].encode()[start:end].decode() == "ほし"
        song = responses[4]
        word = next(
            word for word in song["words"] if word["expected_text"] == "ハッカ色"
        )
        start, end = word["output_span"]
        assert song["romaji"].encode()[start:end].decode() == "hakkairo"
        start, end = word["hiragana_span"]
        assert song["hiragana"].encode()[start:end].decode() == "はっかいろ"
        song = responses[5]
        word = song["words"][1]
        assert word["raw_span"] == [3, 12] and word["expected_text"] == "ぱっと"
        start, end = word["output_span"]
        assert song["romaji"].encode()[start:end].decode() == "patto"
        start, end = word["hiragana_span"]
        assert song["hiragana"].encode()[start:end].decode() == "ぱっと"
    print(
        "Standalone helper passed: relocated path with spaces, clean environment, dictionary and original-byte mapping."
    )


if __name__ == "__main__":
    main()
