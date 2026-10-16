"""Pinned, FA-only HubertFA research adapter; never part of the app package.

Architecture and decoder: wolfgitpr/HubertFA (Apache-2.0), pinned in the
asset manifest. No Lightning, training losses, plotting or NLL checkpoint.
Conditional alignment confidence is NOT independent lyric verification.
"""

import ast
import hashlib
import importlib.util
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).with_name("hubertfa-model-files.json")
TRAINING_BUFFERS = {
    "ph_frame_GHM_loss_fn.GD_ema": [10],
    "ph_frame_GHM_loss_fn.class_ema": [40],
    "ph_edge_GHM_loss_fn.GD_stat_ema": [10],
    "ph_edge_GHM_loss_fn.label_stat_ema_each_class": [3],
    "ph_edge_diff_GHM_loss_fn.GD_stat_ema": [10],
    "ph_edge_diff_GHM_loss_fn.label_stat_ema_each_class": [3],
    "CTC_GHM_loss_fn.ema": [10],
}


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def private_path(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError(
            "Research assets and lyric-bearing output must be outside git."
        )
    return path


def assets(directory, *, download=False):
    """Immutable downloads; verify every byte before importing source/loading weights."""
    directory = private_path(directory)
    manifest = json.loads(ASSETS.read_text())
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.exists() and download:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = path.with_suffix(path.suffix + ".download")
            # A previous interruption may leave only this disposable partial file.
            with (
                urllib.request.urlopen(expected["url"], timeout=90) as source,
                temporary.open("wb") as target,
            ):
                os.chmod(temporary, 0o600)
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if (
                temporary.stat().st_size != expected["size"]
                or digest(temporary) != expected["sha256"]
            ):
                raise ValueError(f"Changed research artifact: {name}")
            temporary.rename(path)
        if (
            path.stat().st_size != expected["size"]
            or digest(path) != expected["sha256"]
        ):
            raise ValueError(f"Unverified research artifact: {name}")
    return manifest


def inference_state(state):
    """Exclude only the seven documented training statistics; no missing layers."""
    if {
        k: list(state[k].shape) for k in TRAINING_BUFFERS if k in state
    } != TRAINING_BUFFERS:
        raise ValueError("Changed checkpoint training buffers.")
    return {k: value for k, value in state.items() if k not in TRAINING_BUFFERS}


def phone_sequence(reference, vocabulary):
    """Insert optional silence at human word markers, not between every phone."""
    phones, owners = ["SP"], [-1]
    previous = None
    seen = set()
    for index, row in enumerate(reference):
        if row["phone"] not in vocabulary or vocabulary[row["phone"]] == 0:
            raise ValueError("Unsupported lexical ARPAbet phone.")
        if previous is not None and previous != row["word"]:
            if row["word"] in seen:
                raise ValueError("Noncontiguous source word ownership.")
            phones.append("SP")
            owners.append(-1)
        phones.append(row["phone"])
        owners.append(index)
        previous = row["word"]
        seen.add(previous)
    if len(phones) == 1:
        raise ValueError("Empty lexical phone target.")
    return phones + ["SP"], owners + [-1]


def feature_indices(sample_count, encoder_frames):
    """Official 20 ms encoder features -> nearest 10 ms grid (ties to even)."""
    if (
        type(sample_count) is not int
        or sample_count < 1103
        or type(encoder_frames) is not int
        or encoder_frames < 1
    ):
        raise ValueError("Expected at least 25 ms of audio and encoder frames.")
    return [
        min(round(index * 0.5), encoder_frames - 1)
        for index in range(sample_count // 441 + 1)
    ]


def decoder_class(source):
    """Retain pinned decoder arithmetic, omit unavailable plotting-only dependencies."""
    tree = ast.parse((source / "tools/decoder.py").read_text())
    tree.body = [
        node
        for node in tree.body
        if not isinstance(node, ast.ImportFrom) or node.module != "tools.plot"
    ]
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            node.body = [
                part
                for part in node.body
                if not isinstance(part, ast.FunctionDef) or part.name != "plot"
            ]
    adapted = source / "decoder_without_plotting.py"
    adapted.write_text(ast.unparse(ast.fix_missing_locations(tree)))
    specification = importlib.util.spec_from_file_location(
        "hubertfa_pinned_decoder", adapted
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.AlignmentDecoder


class ResearchAligner:
    def __init__(self, directory, device="cpu"):
        import torch
        import yaml
        from transformers import HubertModel

        self.directory = private_path(directory)
        self.manifest = assets(self.directory)
        self.device = device
        source = self.directory / "source"
        sys.path.insert(0, str(source))
        from networks.layer.backbone.unet import UNetBackbone
        from networks.layer.block.resnet_block import AttentionResidualBasicBlock
        from networks.layer.fusion.curves_fusion import PowerCurveEdgeFusion
        from networks.layer.scaling.stride_conv import DownSampling, UpSampling

        config = yaml.safe_load((self.directory / "model/config.yaml").read_text())
        self.vocab = yaml.safe_load((self.directory / "model/vocab.yaml").read_text())
        if self.vocab["vocab_size"] != 40 or set(self.vocab["vocab"].values()) != set(
            range(40)
        ):
            raise ValueError("Changed phone inventory.")
        if (
            config["mel_spec_config"]["sample_rate"] != 44100
            or config["mel_spec_config"]["hop_size"] != 441
        ):
            raise ValueError("Changed output clock.")
        self.config = config
        args = config["fa_arg"]

        class Head(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = UNetBackbone(
                    input_dims=768,
                    output_dims=args["hidden_dims"],
                    hidden_dims=args["hidden_dims"],
                    block=AttentionResidualBasicBlock,
                    down_sampling=DownSampling,
                    up_sampling=UpSampling,
                    **{
                        k: args[k]
                        for k in (
                            "down_sampling_factor",
                            "down_sampling_times",
                            "channels_scaleup_factor",
                            "dropout",
                        )
                    },
                )
                self.head = torch.nn.Conv1d(args["hidden_dims"], 42, 1)
                self.curves_edge_fusion = PowerCurveEdgeFusion(
                    args["hidden_dims"], 64, args["curves_attention_dropout"]
                )

            def forward(self, units, curves):
                features = self.backbone(units)
                edges = self.curves_edge_fusion(features, curves).squeeze(1)
                logits = self.head(features)
                return (
                    logits[:, 2:],
                    logits[:, 0] + edges,
                    torch.cat((logits[:, [1]], logits[:, 3:]), dim=1),
                )

        checkpoint = torch.load(
            self.directory / "model/combined.ckpt",
            weights_only=True,
            map_location="cpu",
        )
        recorded = checkpoint["hyper_parameters"]
        if (
            any(
                recorded["config"][key] != config[key]
                for key in ("fa_arg", "hubert_config", "mel_spec_config")
            )
            or recorded["vocab"]["vocab"] != self.vocab["vocab"]
        ):
            raise ValueError(
                "Published config/inventory differs from checkpoint metadata."
            )
        self.head = Head()
        self.head.load_state_dict(
            inference_state(checkpoint["state_dict"]), strict=True
        )
        self.head = self.head.to(device).eval()
        # No custom model code or unrestricted pickle loading.
        self.encoder = (
            HubertModel.from_pretrained(
                self.directory / "encoder", local_files_only=True, weights_only=True
            )
            .to(device)
            .eval()
        )
        if (
            self.encoder.config.hidden_size != 768
            or self.encoder.config.conv_stride != [5, 2, 2, 2, 2, 2, 2]
        ):
            raise ValueError("Changed encoder feature clock.")
        self.decoder = decoder_class(source)(self.vocab, 44100, 441)

    def infer(self, waveform, reference=None, *, ctc_observer=None):
        import numpy as np
        import torch
        from scipy.signal import resample_poly

        if (
            waveform.ndim != 1
            or not np.isfinite(waveform).all()
            or not 1103 <= len(waveform) <= 44100 * 30
        ):
            raise ValueError("Expected finite mono 44.1 kHz, 25 ms–30 s crop.")
        if reference is None and ctc_observer is None:
            raise ValueError("Audio-only inference requires a CTC observer.")
        phones, owners = (
            phone_sequence(reference, self.vocab["vocab"])
            if reference is not None
            else (None, None)
        )
        # The official encoder receives raw waveform without feature-extractor
        # normalization. Existing SciPy polyphase resampling is an explicit variant.
        audio = (
            torch.from_numpy(resample_poly(waveform, 160, 441).astype(np.float32))
            .unsqueeze(0)
            .to(self.device)
        )
        with torch.inference_mode():
            features = self.encoder(audio).last_hidden_state
            indices = torch.tensor(
                feature_indices(len(waveform), features.shape[1]), device=self.device
            )
            units = features[:, indices].transpose(1, 2)
            wav = torch.from_numpy(waveform).to(self.device)
            n_frames = units.shape[-1]
            # Match upstream PowerCurveComputer, including its clamped edge samples.
            centers = torch.arange(n_frames, device=self.device) * 441 + 220
            first = (centers - 441).clamp(min=0)
            windows = (
                first[:, None] + torch.arange(883, device=self.device)[None, :]
            ).clamp(0, len(wav) - 1)
            power = 20 * torch.log10(
                wav[windows].square().mean(1).sqrt().clamp(min=1e-10)
            )
            frame, edge, ctc = self.head(units, power[None, None, :])
        frame, edge, ctc = (x.float().cpu().numpy() for x in (frame, edge, ctc))
        if ctc_observer is not None:
            # This head is unconstrained audio recognition. The optional consumer
            # receives original log probabilities, not a supplied-phone mask.
            ctc_observer((ctc[0] - np.logaddexp.reduce(ctc[0], axis=0)).T)
        if reference is None:
            return [], {"status": "audio_only_ctc", "supplied_phone_reference": False}
        result = [
            {**row, "start_ms": -1, "end_ms": -1, "mean_probability": 0.0}
            for row in reference
        ]
        # Each lexical phone is its own decoder word; optional SP is omitted.
        decoded, conditional = self.decoder.decode(
            frame, edge, len(waveform) / 44100, phones
        )
        observed = [i for i in self.decoder.ph_idx_seq if owners[i] >= 0]
        if len(decoded) != len(observed) or sorted(owners[i] for i in observed) != list(
            range(len(reference))
        ):
            return result, {
                "status": "incomplete",
                "conditional_confidence": float(conditional),
            }
        probability = np.exp(frame[0] - np.logaddexp.reduce(frame[0], axis=0))
        for word, target in zip(decoded, observed, strict=True):
            owner = owners[target]
            start, end = float(word.start * 1000), float(word.end * 1000)
            if not (
                math.isfinite(start)
                and math.isfinite(end)
                and 0 <= start < end <= len(waveform) / 44.1 + 1
            ):
                raise ValueError("Invalid model boundary.")
            first, last = int(start / 10), max(int(start / 10) + 1, math.ceil(end / 10))
            result[owner].update(
                start_ms=start,
                end_ms=end,
                mean_probability=float(
                    probability[self.vocab["vocab"][phones[target]], first:last].mean()
                ),
            )
        greedy = np.argmax(ctc[0], axis=0)
        recognized = [
            int(token)
            for i, token in enumerate(greedy)
            if token and (not i or token != greedy[i - 1])
        ]
        return result, {
            "status": "supplied_phone_path",
            "conditional_confidence": float(conditional),
            "audio_only_ctc_ids": recognized,
            "lexical_verification": False,
        }
