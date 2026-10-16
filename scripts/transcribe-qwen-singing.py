"""Blind cached Qwen ASR with explicit/automatic language routing on bounded audio.

Earlier Japanese-prefilled trials are not an English recognition baseline. Use
the checkpoint's native BF16 dtype and record free-decode confidence separately
from any forced alignment. No prompts, source lyrics or ASR timestamps are supplied.
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import resource
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

spec = importlib.util.spec_from_file_location(
    "blind_audio", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import torch
    from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", choices=("auto", "en", "ja"), default="auto")
    args = parser.parse_args()
    args.manifest, args.model_directory, args.output = map(
        private_path, (args.manifest, args.model_directory, args.output)
    )
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    pin = json.loads((ROOT / "scripts/qwen-singing-files.json").read_text())
    for name, expected in pin["files"].items():
        path = args.model_directory / name
        if (
            path.stat().st_size != expected["size"]
            or digest(path) != expected["sha256"]
        ):
            raise ValueError("Changed official ASR artifact.")
    os.umask(0o077)
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
    )
    torch.set_num_threads(4)
    torch.manual_seed(0)
    started = time.monotonic()
    processor = AutoProcessor.from_pretrained(
        args.model_directory, local_files_only=True, trust_remote_code=False
    )
    model, info = Qwen3ASRForConditionalGeneration.from_pretrained(
        args.model_directory,
        dtype=torch.bfloat16,
        attn_implementation="eager",
        local_files_only=True,
        output_loading_info=True,
    )
    if any(
        info[k]
        for k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
    ):
        raise ValueError(
            "ASR checkpoint does not exactly fill its native architecture."
        )
    model.to("mps").eval()
    load_seconds = time.monotonic() - started
    identity = {
        "manifest_sha256": digest(args.manifest),
        "assets": pin,
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("transcribe-qwen-singing.py", "recognize-singing-phones.py")
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "safetensors", "numpy")
        },
        "dtype": str(model.dtype),
        "language": args.language,
        "source_prompt": None,
        "max_new_tokens": 512,
        "do_sample": False,
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    blind.write(args.output / "identity.json", identity)
    identity_sha, cache, records = digest(args.output / "identity.json"), {}, []
    print(
        json.dumps({"loaded_seconds": load_seconds, "dtype": str(model.dtype)}),
        flush=True,
    )
    for number, case in enumerate(cases, 1):
        began = time.monotonic()
        samples = blind.load_samples(case, args.manifest.parent, cache)
        if len(samples) > 480000:
            raise ValueError("ASR pilot exceeds30seconds.")
        inputs = processor.apply_transcription_request(
            audio=samples,
            language=None if args.language == "auto" else args.language,
            processor_kwargs={"sampling_rate": 16000},
        ).to("mps", model.dtype)
        with torch.inference_mode():
            result = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                return_dict_in_generate=True,
                output_scores=True,
            )
        ids = result.sequences[0, inputs["input_ids"].shape[1] :]
        eos = model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        scores = [
            float(torch.log_softmax(score[0].float(), dim=-1)[token])
            for score, token in zip(result.scores, ids, strict=True)
        ]
        if not all(math.isfinite(x) for x in scores):
            raise ValueError("Nonfinite ASR decoder probabilities.")
        decoded = processor.decode(ids, return_format="parsed")
        row = {
            "id": case["id"],
            "case": case,
            "identity_sha256": identity_sha,
            "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
            "decoded": decoded,
            "decoded_tokens": ids.tolist(),
            "token_log_probabilities": scores,
            "token_strings": processor.tokenizer.convert_ids_to_tokens(ids.tolist()),
            "budget_exhausted": not len(ids) or int(ids[-1]) not in eos,
            "seconds": time.monotonic() - began,
        }
        path = args.output / (hashlib.sha256(case["id"].encode()).hexdigest() + ".json")
        blind.write(path, row)
        records.append({"file": path.name, "sha256": digest(path)})
        del inputs, result
        torch.mps.empty_cache()
        print(
            json.dumps(
                {
                    "completed": number,
                    "total": len(cases),
                    "seconds": row["seconds"],
                    "tokens": len(ids),
                    "budget_exhausted": row["budget_exhausted"],
                    "detected_language": decoded.get("language"),
                }
            ),
            flush=True,
        )
    blind.write(
        args.output / "complete.json",
        {
            "identity_sha256": identity_sha,
            "records": records,
            "load_seconds": load_seconds,
            "seconds": time.monotonic() - started,
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
            "mps_current_allocated_bytes": torch.mps.current_allocated_memory(),
            "mps_driver_allocated_bytes": torch.mps.driver_allocated_memory(),
        },
    )


if __name__ == "__main__":
    main()
