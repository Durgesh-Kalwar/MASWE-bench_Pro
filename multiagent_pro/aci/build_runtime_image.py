#!/usr/bin/env python
"""Build a swe-rex-capable *runtime* image derived from a SWE-bench Pro base image.

Why this exists
---------------
SWE-agent boots each agent with SWE-ReX, whose `DockerDeployment` has two ways to get a
`swerex-remote` server running inside the container, both of which fail on the Pro images
out of the box:

  * `python_standalone_dir` set  -> swe-rex compiles a standalone CPython 3.11 on
    `python:3.11-slim` (glibc 2.36) and copies it into the base image. The Pro images are
    Ubuntu 20.04 (**glibc 2.31**), so the copied binary can't even run `--version`
    (this is the exact `RUN .../python3 --version` boot failure).
  * `python_standalone_dir` None -> swe-rex runs the base image's own `python3`. Pro images
    ship **Python 3.9.5**, but swe-rex `requires-python >= 3.10`, so that path can't run it
    either.

The fix is to bake a swe-rex server into a derived image ONCE, using a portable
python-build-standalone CPython (built for manylinux / glibc 2.17+), which runs fine on the
image's glibc 2.31. `swerex-remote` is symlinked onto PATH, so at solve time swe-rex is
configured with `python_standalone_dir: None` + `pull: never` and simply execs the already
present `swerex-remote` — no per-run compile, no network needed inside the container.

The derived image is content-addressed by (base image, swe-rex version, python tarball) and
cached: `ensure_runtime_image` is a no-op if the tag already exists locally.
"""
import argparse
import hashlib
import subprocess

# Portable CPython (python-build-standalone). `install_only` tarballs extract to a top-level
# `python/` dir with `bin/python3`. Built against an old glibc (2.17+) so it runs on the Pro
# images' glibc 2.31.
PBS_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    "20240814/cpython-3.11.9+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz"
)
# Match the host SWE-ReX client version so the HTTP runtime protocol lines up.
SWEREX_VERSION = "1.2.0"
RUNTIME_PY_PREFIX = "/opt/swerex-python"     # where the portable python lands in the image

_DOCKERFILE = """\
ARG BASE_IMAGE
FROM $BASE_IMAGE
ARG PBS_URL
ARG SWEREX_VERSION
USER root
RUN set -eux; \\
    if ! command -v curl >/dev/null 2>&1; then \\
        apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \\
        && rm -rf /var/lib/apt/lists/*; \\
    fi; \\
    mkdir -p {prefix}; \\
    curl -fsSL "$PBS_URL" -o /tmp/pbs.tar.gz; \\
    tar -xzf /tmp/pbs.tar.gz -C {prefix} --strip-components=1; \\
    rm /tmp/pbs.tar.gz; \\
    {prefix}/bin/python3 --version; \\
    {prefix}/bin/python3 -m pip install --no-cache-dir \\
        --index-url https://pypi.org/simple "swe-rex==$SWEREX_VERSION"; \\
    ln -sf {prefix}/bin/swerex-remote /usr/local/bin/swerex-remote; \\
    swerex-remote --version
""".format(prefix=RUNTIME_PY_PREFIX)


def derived_runtime_tag(base_image: str, *, swerex_version: str = SWEREX_VERSION,
                        pbs_url: str = PBS_URL) -> str:
    """Deterministic local tag for the swe-rex runtime image derived from ``base_image``.

    Content-addressed by (base image, swe-rex version, python tarball) so a change to any of
    them yields a fresh tag (and thus a rebuild), while identical inputs reuse the cache.
    """
    digest = hashlib.sha256(
        "\n".join([base_image, swerex_version, pbs_url]).encode()).hexdigest()[:16]
    return f"swerex-runtime:{digest}"


def _image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def ensure_runtime_image(base_image: str, *, swerex_version: str = SWEREX_VERSION,
                         pbs_url: str = PBS_URL, quiet: bool = False) -> str:
    """Build (if missing) the swe-rex runtime image derived from ``base_image``; return its tag.

    Idempotent and cached: returns immediately if the derived tag already exists locally.
    """
    tag = derived_runtime_tag(base_image, swerex_version=swerex_version, pbs_url=pbs_url)
    if _image_exists(tag):
        if not quiet:
            print(f"  runtime image cached: {tag}")
        return tag
    if not quiet:
        print(f"  building runtime image {tag} from {base_image} ...")
    cmd = [
        "docker", "build", "-t", tag,
        "--build-arg", f"BASE_IMAGE={base_image}",
        "--build-arg", f"PBS_URL={pbs_url}",
        "--build-arg", f"SWEREX_VERSION={swerex_version}",
        "-",
    ]
    proc = subprocess.run(cmd, input=_DOCKERFILE.encode(),
                          stdout=(subprocess.DEVNULL if quiet else None),
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to build swe-rex runtime image from {base_image}:\n"
            f"{proc.stderr.decode(errors='replace')}")
    if not quiet:
        print(f"  built {tag}")
    return tag


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_image", help="Pro base image (jefzda/sweap-images:<tag>)")
    ap.add_argument("--swerex-version", default=SWEREX_VERSION)
    ap.add_argument("--print-tag-only", action="store_true",
                    help="Just print the deterministic derived tag; do not build")
    args = ap.parse_args()
    if args.print_tag_only:
        print(derived_runtime_tag(args.base_image, swerex_version=args.swerex_version))
        return
    tag = ensure_runtime_image(args.base_image, swerex_version=args.swerex_version)
    print(tag)


if __name__ == "__main__":
    main()
