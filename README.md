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

## Licences

Every pack lists its components and their licences in `THIRD-PARTY-NOTICES.txt`, with the full
texts in `licenses/`. The same notices are attached to each release. Versions are pinned in
`requirements.in` and `runtime.json`.

FFmpeg is LGPL-2.1-or-later. Its complete source is attached to every release, and you may
replace the FFmpeg libraries in a pack with your own build. On macOS, the GPL FFmpeg bundled with
OpenCV's PyPI wheel is removed and an LGPL build is used instead ([`tools/ffmpeg.sh`](tools/ffmpeg.sh)).

The scripts in this repository are under the [MIT licence](LICENSE), which does not cover the
software in the packs.
