"""Research-only audio-only singing letter streams; never source-conditioned text."""

import json

from audio_first_models import ROOT, digest


def decode_letters(ids, vocabulary):
    inverse = {v: k for k, v in vocabulary.items()}
    if set(inverse) != set(range(32)):
        raise ValueError("Changed singing character inventory.")
    # Special predictions remain observable, never silently improve word coverage.
    return "".join(inverse[i].replace("|", " ") for i in ids)


def load(directory):
    import torch
    from safetensors.torch import load_file
    from transformers import Wav2Vec2Config, Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    pin = json.loads((ROOT / "scripts/echora-model-files.json").read_text())
    for name, row in pin["files"].items():
        path = directory / name
        if path.stat().st_size != row["size"] or digest(path) != row["sha256"]:
            raise ValueError("Changed pinned singing letter asset.")
    config = Wav2Vec2Config.from_json_file(directory / "config.json")
    config._attn_implementation = "eager"
    if (
        config.hidden_size != 1024
        or config.vocab_size != 32
        or config.pad_token_id != 29
        or config.num_hidden_layers != 24
        or not config.stream2_head
    ):
        raise ValueError("Different dual-stream CTC architecture.")
    with torch.device("meta"):
        model = Wav2Vec2ForCTC(config)
        model.stream2_head = torch.nn.Linear(1024, 32)
    state = load_file(directory / "model.safetensors", device="cpu")
    model.load_state_dict(state, strict=True, assign=True)
    del state
    model.to("mps", dtype=torch.float32).eval()
    settings = json.loads((directory / "processor_config.json").read_text())[
        "feature_extractor"
    ]
    if settings["sampling_rate"] != 16000 or settings["do_normalize"] is not True:
        raise ValueError("Different singing waveform normalization.")
    processor = Wav2Vec2FeatureExtractor(**settings)
    vocabulary = {
        **json.loads((directory / "vocab.json").read_text()),
        "<s>": 30,
        "</s>": 31,
    }

    def infer(samples):
        inputs = processor(samples, sampling_rate=16000, return_tensors="pt").to("mps")
        with torch.inference_mode():
            hidden = model.wav2vec2(**inputs).last_hidden_state
            hidden = model.dropout(hidden)
            result = {
                name: head(hidden)[0].float().log_softmax(-1).cpu().numpy()
                for name, head in (
                    ("lead", model.lm_head),
                    ("secondary", model.stream2_head),
                )
            }
        return result

    return infer, {
        "assets": pin,
        "vocabulary": vocabulary,
        "blank": 29,
        "stride_samples": 320,
        "receptive_field_samples": 400,
        "source_conditioned": False,
        "precision": "float32",
    }
