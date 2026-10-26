# Licence texts a wheel leaves out

A wheel on PyPI sometimes declares its licence in its metadata without including the text, or bundles another
project's binaries without that project's licence. `tools/build.py` copies everything under `<package>/` here into
the pack's `licenses/<package>/`, and fails the build for any package that ends up with no licence text at all.

| Package | File | From |
|---|---|---|
| flatbuffers 25.12.19 | `flatbuffers/LICENSE` (Apache-2.0) | https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE |
| onnxruntime-ep-webgpu 0.4.0 (Windows) | `onnxruntime-ep-webgpu/DXC/LICENSE-MS.txt`, `LICENSE-LLVM.txt`, `LICENSE-MIT.txt` | the DirectX Shader Compiler release the add-on's `dxcompiler.dll` and `dxil.dll` come from (both version 1.8.2502.8): https://github.com/microsoft/DirectXShaderCompiler/releases/tag/v1.8.2502, `dxc_2025_02_20.zip` (sha256 `70b1913a1bfce4a3e1a5311d16246f4ecdf3a3e613abec8aa529e57668426f85`) |
