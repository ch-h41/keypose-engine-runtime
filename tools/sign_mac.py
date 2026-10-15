#!/usr/bin/env python3
"""Signs the macOS pack with a Developer ID and has Apple notarise it, on the Mac that holds the certificate (it never
goes to CI), then publishes the release CI left as a draft.

    python3 tools/sign_mac.py v1.0.0                     the draft release: sign its macOS pack, update it, publish
    python3 tools/sign_mac.py --pack PACK --out DIR      a local pack: write the signed one to DIR (nothing uploaded)

  --identity SHA1   which certificate (default: the Developer ID Application one that expires last)
  --profile NAME    the notarytool keychain profile (default: keypose; made once with `xcrun notarytool
                    store-credentials keypose --apple-id ... --team-id ...`)
  --mediapipe-model holistic_landmarker.task for the smoke test (default: build/holistic_landmarker.task, as CI uses)

What it does to the pack:
  1. every Mach-O file is signed with the hardened runtime and a secure timestamp: the libraries, then the python
     executable (a pack has no app bundles, so each file carries its own signature)
  2. a zip of the folder is notarised (notarytool submit --wait). A .tar.gz cannot be stapled; Gatekeeper finds the
     ticket online, and only ever asks for files that are quarantined
  3. the signed python runs tools/smoke.py (the hardened runtime is what could break it), and so does a copy with
     every binary quarantined, which Gatekeeper lets run only when it is notarised
  4. it is packed as build.py packs it, with "macos_signing" added to keypose-runtime.json

Drive it with Python 3.14 or later, as build.py."""
import argparse, json, os, re, shutil, subprocess, sys, tarfile, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT, REPO_URL, write_tar, sha256, log, fail   # noqa: E402

PLAT = "darwin-arm64"
REPO = re.sub(r"^https://github.com/", "", REPO_URL)
MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def run(cmd, **kw):
    r = subprocess.run(cmd, text=True, capture_output=True, **kw)
    if r.returncode:
        fail(f"{' '.join(cmd[:3])}... failed:\n{(r.stdout + r.stderr)[-3000:]}")
    return r.stdout


def identity(want):
    """-> (SHA-1, name) of the signing certificate: `want`, else the Developer ID Application one that expires last."""
    found = re.findall(r'^\s*\d+\) ([0-9A-F]{40}) "(Developer ID Application: [^"]+)"', run(["security", "find-identity", "-v", "-p", "codesigning"]), re.M)
    if want:
        hit = [f for f in found if f[0] == want.upper()]
        if not hit: fail(f"no valid Developer ID Application identity {want} in the keychain")
        return hit[0]
    if not found: fail("no Developer ID Application certificate in the keychain (Xcode > Settings > Accounts > Manage Certificates)")
    pems = run(["security", "find-certificate", "-a", "-Z", "-p", "-c", "Developer ID Application"])
    ends = {}
    for sha, pem in re.findall(r"SHA-1 hash: ([0-9A-F]{40})\n(-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----)", pems, re.S):
        end = run(["openssl", "x509", "-noout", "-enddate"], input=pem).strip().split("=", 1)[1]
        ends[sha] = time.mktime(time.strptime(end.replace("  ", " "), "%b %d %H:%M:%S %Y %Z"))
    return max(found, key=lambda f: ends.get(f[0], 0))


def machos(rt):
    """-> (libraries, executables): every Mach-O file under rt, symlinks left out (they point at one of these)."""
    libs, exes = [], []
    for top, dirs, files in os.walk(rt):
        dirs.sort()
        for n in sorted(files):
            p = os.path.join(top, n)
            if os.path.islink(p): continue
            with open(p, "rb") as f:
                if f.read(4) not in MACHO: continue
            (exes if os.access(p, os.X_OK) and "/bin/" in p else libs).append(p)
    return libs, exes


def notarise(rt, profile, work):
    """-> the submission id, once Apple has accepted every binary in rt."""
    z = os.path.join(work, "notarise.zip")
    run(["ditto", "-c", "-k", "--keepParent", rt, z])
    log(f"notarising {os.path.getsize(z) / 1e6:.0f} MB (usually a few minutes)")
    r = subprocess.run(["xcrun", "notarytool", "submit", z, "--keychain-profile", profile, "--wait", "--timeout", "2h",
                        "--output-format", "json"], text=True, capture_output=True)
    try: res = json.loads(r.stdout)
    except ValueError: fail(f"notarytool: {(r.stdout + r.stderr)[-2000:]}")
    if res.get("status") != "Accepted":
        detail = subprocess.run(["xcrun", "notarytool", "log", res.get("id", "?"), "--keychain-profile", profile], text=True, capture_output=True).stdout
        fail(f"notarisation {res.get('status')}: {res.get('message')}\n{detail[-4000:]}")
    os.remove(z)
    return res["id"]


def check(rt, model, work):
    """The signed python passes the smoke test (CoreML required), and so does a copy with every binary quarantined:
    Gatekeeper then checks each one as it loads, and lets only notarised code run."""
    def smoke(root, what):
        cmd = [os.path.join(root, "bin", "python3"), "-E", "-s", os.path.join(ROOT, "tools", "smoke.py"), os.path.join(work, "smoke.json")] + ([model] if model else [])
        r = subprocess.run(cmd, text=True, capture_output=True, cwd=work, env=dict(os.environ, KEYPOSE_SMOKE_GPU="require"), timeout=900)
        if r.returncode: fail(f"{what} fails the smoke test:\n{(r.stdout + r.stderr)[-4000:]}")
    smoke(rt, "the signed runtime")
    log("smoke test passed with the signed runtime" + ("" if model else " (no MediaPipe model given: its check skipped)"))
    q = os.path.join(work, "quarantined")
    shutil.copytree(rt, q, symlinks=True)
    try:
        stamp = f"0081;{int(time.time()):x};keypose sign_mac;"
        for p in sum(machos(q), []): run(["xattr", "-w", "com.apple.quarantine", stamp, p])
        smoke(q, "a quarantined copy (Gatekeeper)")
    finally:
        shutil.rmtree(q, ignore_errors=True)
    log("smoke test passed with every binary quarantined: Gatekeeper accepts them (notarised)")


def sign_pack(pack, out, want, profile, model):
    """Signs and notarises pack (a darwin-arm64 .tar.gz) into out/<same name>. -> its engine-runtime.json entry fields."""
    sha, name = identity(want)
    log(f"signing with {name} ({sha})")
    work = tempfile.mkdtemp(prefix="keypose-sign-")
    try:
        with tarfile.open(pack, "r:gz") as t: t.extractall(work, filter="tar")
        rt = os.path.join(work, "keypose-runtime")
        libs, exes = machos(rt)
        if not exes: fail("no python executable in the pack")
        base = ["codesign", "--force", "--timestamp", "--options", "runtime", "--sign", sha]
        for i in range(0, len(libs), 20): run(base + libs[i:i + 20])
        run(base + exes)
        for p in libs + exes: run(["codesign", "--verify", "--strict", p])
        log(f"signed {len(libs)} libraries and {len(exes)} executable(s)")
        sub = notarise(rt, profile, work)
        log(f"notarised: Accepted ({sub})")
        check(rt, model, work)
        mpath = os.path.join(rt, "keypose-runtime.json")
        m = json.load(open(mpath, encoding="utf-8"))
        m["macos_signing"] = {"identity": name, "hardened_runtime": True, "notarization": sub,
                              "signed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open(mpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(m, f, indent=1)
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, os.path.basename(pack))
        unpacked = write_tar(rt, path, False)
        return {"sha256": sha256(path), "size": os.path.getsize(path), "unpacked": unpacked}, path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def gh(*a):
    return run(["gh", *a, "-R", REPO])


def release(tag, want, profile, model):
    info = json.loads(gh("release", "view", tag, "--json", "isDraft,body,assets"))
    if not info["isDraft"]: fail(f"{tag} is already published: only a draft (as CI leaves it) is signed")
    work = tempfile.mkdtemp(prefix="keypose-release-")
    try:
        gh("release", "download", tag, "-D", work, "-p", f"*-{PLAT}.tar.gz", "-p", "engine-runtime.json", "-p", "SHA256SUMS")
        pack = [os.path.join(work, n) for n in os.listdir(work) if n.endswith(f"-{PLAT}.tar.gz")][0]
        name = os.path.basename(pack)
        sums = open(os.path.join(work, "SHA256SUMS"), encoding="utf-8").read()
        if f"{sha256(pack)}  {name}" not in sums: fail(f"{name} does not match the draft's SHA256SUMS")
        fields, signed = sign_pack(pack, os.path.join(work, "signed"), want, profile, model)
        man = json.load(open(os.path.join(work, "engine-runtime.json"), encoding="utf-8"))
        old = man["platforms"][PLAT]
        man["platforms"][PLAT] = dict(old, **fields)
        with open(os.path.join(work, "engine-runtime.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(man, f, indent=1); f.write("\n")
        new_sums = sums.replace(f"{old['sha256']}  {name}", f"{fields['sha256']}  {name}")
        # engine-runtime.json is in SHA256SUMS too
        new_sums = re.sub(r"^[0-9a-f]{64}  engine-runtime\.json$", f"{sha256(os.path.join(work, 'engine-runtime.json'))}  engine-runtime.json", new_sums, flags=re.M)
        open(os.path.join(work, "SHA256SUMS"), "w", encoding="utf-8", newline="\n").write(new_sums)
        body = info["body"].replace(old["sha256"], fields["sha256"]).replace(f"| {old['size'] / 1e6:.0f} MB |", f"| {fields['size'] / 1e6:.0f} MB |")
        body += "\nThe macOS pack is signed with a Developer ID and notarised by Apple (tools/sign_mac.py).\n"
        open(os.path.join(work, "notes.md"), "w", encoding="utf-8").write(body)
        shutil.move(signed, pack)
        gh("release", "upload", tag, pack, os.path.join(work, "engine-runtime.json"), os.path.join(work, "SHA256SUMS"), "--clobber")
        gh("release", "edit", tag, "--notes-file", os.path.join(work, "notes.md"), "--draft=false")
        log(f"published {tag}: {name} sha256 {fields['sha256']} ({fields['size'] / 1e6:.1f} MB)")
        print(json.dumps(man, indent=1))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    if sys.platform != "darwin": fail("this signs with the macOS keychain: run it on the Mac with the certificate")
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", nargs="?")
    ap.add_argument("--pack"); ap.add_argument("--out")
    ap.add_argument("--identity"); ap.add_argument("--profile", default="keypose")
    ap.add_argument("--mediapipe-model", default=os.path.join(ROOT, "build", "holistic_landmarker.task"))
    a = ap.parse_args()
    model = a.mediapipe_model if a.mediapipe_model and os.path.isfile(a.mediapipe_model) else None
    if a.pack:
        fields, path = sign_pack(os.path.abspath(a.pack), os.path.abspath(a.out or "dist-signed"), a.identity, a.profile, model)
        print(json.dumps(dict(fields, file=path), indent=1))
    elif a.tag:
        release(a.tag, a.identity, a.profile, model)
    else:
        ap.error("give a release tag, or --pack")


if __name__ == "__main__":
    main()
