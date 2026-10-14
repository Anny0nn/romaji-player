"""Pinned research-only acoustic adapters. Inputs are waveforms, never lyrics."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa/vendor")]


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError("Pinned acoustic asset changed.")


def expanded_phones(ids, vocabulary):
    from singing_phonemes import token_phones

    result = []
    inverse = {v: k for k, v in vocabulary.items()}
    for label in ids:
        token = inverse[label]
        result.extend(token_phones(token) or [f"unsupported:{token}"])
    return result


def kana_sequence_phones(kana):
    from g2p.converters.japanese import _KANA_TO_ROMAJI
    from singing_phonemes import token_phones

    phones, index = [], 0
    small = dict(zip("ぁぃぅぇぉ", "aiueo", strict=True))
    while index < len(kana):
        token = kana[index]
        if token == "ん":
            phones.append("N")
        elif token == "ー":
            phones.append(
                phones[-1] if phones and phones[-1] in "aeiou" else "unsupported:ー"
            )
        elif kana[index : index + 2] in _KANA_TO_ROMAJI:
            phones.extend(token_phones(_KANA_TO_ROMAJI[kana[index : index + 2]]))
            index += 1
        else:
            value = _KANA_TO_ROMAJI.get(token, small.get(token))
            phones.extend(token_phones(value) if value else [f"unsupported:{token}"])
        index += 1
    return phones


def source_word_phones(word):
    """Use the converter's particle pronunciation, retaining its written kana."""
    from singing_phonemes import kana_phones

    kana, roman = word["hiragana"], word["romaji"]
    phones = kana_phones(kana, roman)
    if phones is not None:
        return phones
    return kana_sequence_phones(kana)


def load_romaji(folder):
    import torch
    from reading_repair import SINGING_FILES, singing_model

    verify(
        folder / "singing/model_safetensors.zip",
        "76e1cd94bb4b6ac0a0e2736ea816077a4484c1a6b06afa88688122c714a39d25",
    )
    model, vocabulary = singing_model(folder)
    meta = {
        "assets": SINGING_FILES,
        "precision": "float32",
        "heads": {"romaji": vocabulary},
        "blank": model.config.pad_token_id,
        "stride_samples": 320,
        "receptive_field_samples": 400,
        "input_normalization": "none; shipped singing_evidence path",
    }

    def infer(samples):
        with torch.inference_mode():
            logits = model(torch.from_numpy(samples.copy())[None].to("mps")).logits
            return {"romaji": logits[0].float().log_softmax(-1).cpu().numpy()}

    return infer, meta


def load_kana(folder, source, precision):
    import torch
    from transformers import Wav2Vec2Config, Wav2Vec2FeatureExtractor, Wav2Vec2Model

    pinned = json.loads((ROOT / "scripts/audio-first-model-files.json").read_text())
    checkpoint = folder / pinned["kana_checkpoint"]["filename"]
    verify(checkpoint, pinned["kana_checkpoint"]["sha256"])
    verify(folder / "backbone/config.json", pinned["backbone_config_sha256"])
    for name, expected in pinned["source_files"].items():
        verify(source / name, expected)
    sys.path.insert(0, str(source))
    from src.asr.kana_vocab import KanaVocab
    from src.asr.model import DualCTCModel
    from src.asr.phoneme_vocab import PhonemeVocab

    config = Wav2Vec2Config.from_pretrained(folder / "backbone", local_files_only=True)
    config._attn_implementation = "eager"
    if config.num_hidden_layers != 24 or config.hidden_size != 1024:
        raise ValueError("Wrong kana encoder configuration.")
    kana, phones = KanaVocab(), PhonemeVocab()
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if (
        state["pretrained"] != "reazon-research/japanese-wav2vec2-large"
        or state["inter_ctc_layer"] != 12
    ):
        raise ValueError("Wrong kana checkpoint architecture.")
    model = DualCTCModel(Wav2Vec2Model(config), kana.size, phones.size, 1024, 12)
    model.load_state_dict(state["model_state_dict"], strict=True)
    del state
    dtype = torch.float32 if precision == "float32" else torch.float16
    model.to("mps", dtype).eval()
    extractor = Wav2Vec2FeatureExtractor(
        sampling_rate=16000, do_normalize=True, return_attention_mask=True
    )
    meta = {
        "assets": pinned,
        "precision": precision,
        "heads": {"kana": kana.stoi, "kana-phone": phones.stoi},
        "blank": 0,
        "stride_samples": 320,
        "receptive_field_samples": 400,
        "input_normalization": "Wav2Vec2FeatureExtractor; zero mean/unit variance",
    }

    def infer(samples):
        inputs = extractor(samples, sampling_rate=16000, return_tensors="pt")
        with torch.inference_mode():
            logits = model(
                inputs.input_values.to("mps", dtype),
                attention_mask=inputs.attention_mask.to("mps"),
            )
        return {
            name: logits[key][0].float().log_softmax(-1).cpu().numpy()
            for name, key in (("kana", "kana_logits"), ("kana-phone", "phoneme_logits"))
        }

    return infer, meta
