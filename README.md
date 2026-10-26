# Keypose engine runtime

The Python runtime that Keypose's tracking engine runs on. The Keypose panel downloads it on
first run and checks its sha256 before installing it.

| Platform | Needs |
|---|---|
| macOS, Apple silicon | macOS 14 or later |
| Windows, x64 | Windows 10 or 11 |

Intel Macs are not supported.

## Installing offline

If github.com is blocked, download the pack for your platform from [Releases](../../releases),
then click **install it from the file** on Keypose's setup screen. It is still checked against
its sha256.

## Signing

On Windows, `python.exe` and the Python DLLs are python.org's own, signed by the Python Software
Foundation. The macOS pack is signed with a Developer ID (hardened runtime, secure timestamp) and
notarised by Apple. CI builds both packs into a draft release, and [`tools/sign_mac.py`](tools/sign_mac.py)
signs, notarises and tests the macOS pack on the Mac that holds the certificate, then publishes it.

## Licences

Every pack lists its components and their licences in `THIRD-PARTY-NOTICES.txt`, with the full
texts in `licenses/`. The same notices are attached to each release. Versions are pinned in
`requirements.in` and `runtime.json`.

The Windows pack includes ONNX Runtime's WebGPU add-on, which runs the engine on any DirectX 12 GPU. It
bundles Microsoft's DirectX Shader Compiler; `dxil.dll` is under Microsoft's own licence terms for it
(`licenses/onnxruntime-ep-webgpu/DXC/LICENSE-MS.txt`), the rest is open source. The macOS pack includes
coremltools, which runs Keypose's High quality body model on the Neural Engine.

FFmpeg is LGPL-2.1-or-later. Its complete source is attached to every release, and you may
replace the FFmpeg libraries in a pack with your own build. On macOS, the GPL FFmpeg bundled with
OpenCV's PyPI wheel is removed and an LGPL build is used instead ([`tools/ffmpeg.sh`](tools/ffmpeg.sh)).

The scripts in this repository are under the [MIT licence](LICENSE), which does not cover the
software in the packs.
