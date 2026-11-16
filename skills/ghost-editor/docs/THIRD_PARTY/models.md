# Models

| model | used by | licence | how it gets here |
|---|---|---|---|
| MediaPipe Face Landmarker `face_landmarker.task` (BlazeFace short range + Face Mesh V2 + Blendshape V2, float16 v1) | `scripts/facescan.py`, `scripts/headangle.py` (gaze, blinks, head angle) | Apache-2.0 (Google; model cards) | **bundled** unmodified in `library/models/`, licence in `library/models/LICENSE-mediapipe-face-landmarker.txt` |
| YuNet `face_detection_yunet_2023mar.onnx` | `face_track.py`, `broll_qa.py`, `headpose.py`, `headmotion.py`, the Seoul list prep | MIT (opencv_zoo) | downloaded on first use into `library/models/` |
| SFace `face_recognition_sface_2021dec.onnx` | `broll_qa.py` (who is on screen), `own_footage.py` (only you in your own footage) | Apache-2.0 (opencv_zoo) | downloaded on first use |
| BiRefNet weights | `matte.py`, `cutout_fx.py` | MIT (ZhengPeng7) | optional venv, see [matte.md](matte.md) |
| silero-vad, ClearerVoice / MossFormer2 | audio QA | MIT / Apache-2.0 | optional venv, see [audioqa.md](audioqa.md) |
| DeepFilterNet3 | `scripts/denoise.sh` | MIT / Apache-2.0 | pip into `.venv-df` on first use |
| Whisper | `transcribe.py` | MIT (openai-whisper) | you install it (`pip install openai-whisper`) |
