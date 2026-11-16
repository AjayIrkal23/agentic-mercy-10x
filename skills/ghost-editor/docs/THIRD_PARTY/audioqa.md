# Third-party code and weights: audio QA

Venv `~/.venvs/ghost-audioqa` and weights in `~/.cache/ghost-audioqa`, both made by `scripts/setup_audioqa.sh`; nothing
below is committed.

| What | Source | Licence | How it is used |
|---|---|---|---|
| ClearerVoice-Studio (`clearvoice` 0.1.2) | https://github.com/modelscope/ClearerVoice-Studio | Apache-2.0 | Library imported by `scripts/voice_enhance.py`. At run time `clearvoice.utils.decode.bandwidth_sub` is swapped for our own band merge (`detect_cutoff` + `merge_bands`). |
| MossFormer2_SE_48K / MossFormer2_SR_48K weights | https://huggingface.co/alibabasglab | Apache-2.0 (model cards) | Downloaded at setup (`voice_enhance.py --fetch-only`), inference files only (the SR repo's 1.7 GB training checkpoint is skipped). |
| silero-vad 6.2.3 (weights inside the package) | https://github.com/snakers4/silero-vad | MIT | Imported by `scripts/vad_pauses.py`. |
| pyloudnorm, torch/torchaudio/torchvision, numpy, opencv-python, soundfile, matplotlib | PyPI | MIT / BSD / Apache-2.0 / PSF-style | venv dependencies. |

No GPL/AGPL code was used.
