# Third-party code, weights and ideas: person matte (`scripts/matte.py`) and cutout effects (`scripts/cutout_fx.py`)

Nothing below is vendored in the repo. Weights and model code download at setup or first use into `~/.cache/ghost-matte/`
and `~/.rembg/models/`; the venv is `~/.venvs/ghost-matte` (`scripts/setup_matte.sh`).

| What | Source | Licence | How it is used |
|---|---|---|---|
| rembg 2.0.85 | https://github.com/danielgatis/rembg | MIT | pip dependency. `rembg.new_session(<name>)` downloads the BiRefNet ONNX files and builds the ONNX Runtime session for `--backend ort`. Its `predict()` is not used (it min/max-stretches every frame, so the alpha pumps). rembg's default model `bria-rmbg` is refused in code: BRIA weights need a paid licence. |
| BiRefNet model code (`birefnet.py`, `BiRefNet_config.py`) | https://huggingface.co/ZhengPeng7/BiRefNet-portrait (repo https://github.com/ZhengPeng7/BiRefNet) | MIT | Loaded at run time through `transformers` `trust_remote_code` from the local cache for `--backend torch` (Apple MPS). Not modified, not vendored. |
| BiRefNet-portrait weights | HF ZhengPeng7/BiRefNet-portrait; rembg release v0.0.0 | MIT | Default model; commercial use allowed. |
| BiRefNet-HRSOD / BiRefNet_lite weights | HF ZhengPeng7/BiRefNet-HRSOD, ZhengPeng7/BiRefNet_lite; rembg release v0.0.0 | MIT | Optional (`--model birefnet-hrsod`, `birefnet-general-lite`). |
| BiRefNet family weights for `cutout_fx.py`: BiRefNet_lite (default), BiRefNet (general), BiRefNet-DIS5K, BiRefNet-COD, BiRefNet-HRSOD, BiRefNet_HR, BiRefNet-matting, BiRefNet_HR-matting, BiRefNet_lite-matting, BiRefNet_lite-2K, BiRefNet_dynamic, BiRefNet_dynamic-matting | huggingface.co/ZhengPeng7/* (model cards: `license: mit`) | MIT | `setup_matte.sh` caches BiRefNet_lite; the others download on first use into `~/.cache/ghost-matte/hf` (never the repo). Model code loaded with `trust_remote_code` from that folder, not modified, not vendored. |
| Montserrat (woff2 subsets) | the skill's `templates/fonts` | OFL-1.1 | display type in cutout_fx.py (sandwich words, cover headlines, labels) |
| BEN2 base ONNX | https://huggingface.co/PramaLLC/BEN2 | MIT | Optional (`--model ben2-base`, ORT only). |
| Guided filter / fast guided filter | He, Sun, Tang (ECCV 2010, TPAMI 2013); He & Sun, arXiv:1505.00996 | paper (algorithm) | Own numpy/OpenCV implementation (`fast_guided_upsample`), imported by cutout_fx.py. |
| Blur-fusion foreground estimation | Forte & Pitie, ICIP 2021, arXiv:2006.14970 | paper (algorithm) | Own implementation of the published equations (`blur_fusion_fields`). |
| PyTorch, torchvision, transformers, timm, kornia, einops, onnxruntime, opencv-python-headless, numpy, Pillow | PyPI | BSD-3 / BSD-3 / Apache-2.0 / Apache-2.0 / Apache-2.0 / MIT / MIT / Apache-2.0 / BSD-3 / MIT-CMU (HPND) | pip dependencies in the venv (`scripts/matte-requirements.txt`). |
| cutout effects (light wrap, lens blur in linear light, die-cut sticker stroke, neon trace, SDF frames, sharpest-frame pick) | own code | the skill's licence | `scripts/cutout_fx.py`; textbook compositing techniques, nothing copied |

Not used: BRIA RMBG 1.4/2.0 (non-commercial / paid), RobustVideoMatting (GPL-3.0), MODNet weights (CC BY-NC-SA).
