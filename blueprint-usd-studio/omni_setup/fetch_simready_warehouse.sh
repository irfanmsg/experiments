#!/usr/bin/env bash
set -euo pipefail

asset_root="${BLUEPRINT_STUDIO_ASSET_ROOT:-/home/ovqa/Repos/OmniverseAssets}"
archive="$asset_root/archives/SimReady_Warehouse_01_NVD@10010.zip"
output="$asset_root/SimReady_Warehouse_01"
marker="$output/.simready_archive_sha256"
sample="$output/Assets/simready_content/common_assets/props/recycledwoodpallet_a01/recycledwoodpallet_a01.usd"
url='https://d4i3qtqj3r0z5.cloudfront.net/SimReady_Warehouse_01_NVD%4010010.zip'
expected_bytes=14168807282
expected_sha256='a8bfeb64c409d032d0652b31955791b495b71659c5a9c5a23a2a907022627a9f'

mkdir -p "$(dirname "$archive")" "$output"
actual_bytes=0
if [[ -f "$archive" ]]; then actual_bytes="$(stat -c '%s' "$archive")"; fi
if (( actual_bytes != expected_bytes )); then
  curl --fail --location --retry 5 --retry-all-errors --retry-delay 5 \
    --continue-at - --progress-bar --output "$archive" "$url"
fi

actual_bytes="$(stat -c '%s' "$archive")"
if (( actual_bytes != expected_bytes )); then
  printf 'Incomplete warehouse archive: %s of %s bytes\n' "$actual_bytes" "$expected_bytes" >&2
  exit 1
fi
actual_sha256="$(sha256sum "$archive" | cut -d ' ' -f 1)"
if [[ "$actual_sha256" != "$expected_sha256" ]]; then
  printf 'Warehouse archive SHA-256 did not match the verified download\n' >&2
  exit 1
fi
if [[ -f "$marker" && -f "$sample" ]] && [[ "$(cat "$marker")" == "$expected_sha256" ]]; then
  printf 'SimReady warehouse pack is already extracted at %s\n' "$output"
  exit 0
fi

python3 - "$archive" "$output" <<'PY'
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

archive, output = (Path(p) for p in sys.argv[1:])
base = output.resolve()
with zipfile.ZipFile(archive) as source:
    members = source.infolist()
    for item in members:
        relative = PurePosixPath(item.filename)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'Unsafe path in asset archive: {item.filename}')
        mode = item.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f'Symlink in asset archive: {item.filename}')
        destination = base.joinpath(*relative.parts).resolve()
        if not destination.is_relative_to(base):
            raise ValueError(f'Unsafe path in asset archive: {item.filename}')

    print(f'Validating {len(members)} archive entries and CRCs...', flush=True)
    bad = source.testzip()
    if bad:
        raise ValueError(f'Corrupt archive entry: {bad}')

    print(f'Extracting into {base}...', flush=True)
    for item in members:
        destination = base.joinpath(*PurePosixPath(item.filename).parts)
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as reader, destination.open('wb') as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)

    print(f'Extracted {len(members)} entries.', flush=True)
PY
printf '%s\n' "$expected_sha256" > "$marker"
