"""Supporting evidence uploads; independent of plan edits and geometry extraction."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
import uuid

import pymupdf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image


UPLOADS = Path(__file__).resolve().parents[1] / 'uploads'
MAX_BYTES = 200 * 1024 * 1024
MAX_FILES = 20
STATUS = 'supporting evidence; not automatically extracted'
FORMATS = {'.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg',
           '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.tif': 'image/tiff', '.tiff': 'image/tiff'}
SourceRole = Literal['blueprint', 'detail', 'measurement', 'photo', 'finish', 'style', 'other']
router = APIRouter()


def _directory(project_id):
    if not re.fullmatch(r'[a-z0-9_-]{1,128}', project_id):
        raise HTTPException(400, 'Invalid project ID')
    project = UPLOADS / project_id
    if project.resolve().parent != UPLOADS.resolve() or not (project / 'plan.json').is_file():
        raise HTTPException(404, 'Project not found')
    directory = project / 'sources'
    if directory.is_symlink():
        raise HTTPException(400, 'Invalid source directory')
    return directory


def _entries(directory):
    index = directory / 'index.json'
    if not index.exists():
        return []
    try:
        entries = json.loads(index.read_text())
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('Invalid manifest')
        return entries
    except (OSError, ValueError) as exc:
        raise HTTPException(500, 'Supporting source index could not be read; existing files are preserved') from exc


def source_manifest(project_id):
    return {'project_id': project_id, 'sources': _entries(_directory(project_id))}


def _validate_source(path, suffix):
    try:
        if suffix == '.pdf':
            with pymupdf.open(path, filetype='pdf') as document:
                if not document.is_pdf or document.needs_pass or document.page_count == 0:
                    raise ValueError('Use a readable, unencrypted PDF with at least one page')
        else:
            with Image.open(path) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP', 'TIFF'} or image.width * image.height > 100_000_000:
                    raise ValueError('Use a supported image under 100 megapixels')
                if Image.MIME.get(image.format) != FORMATS[suffix]:
                    raise ValueError('Image contents do not match the file extension')
                image.verify()
    except (OSError, ValueError, pymupdf.FileDataError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, 'Use a readable PDF or supported image under 100 megapixels') from exc


@router.get('/api/projects/{project_id}/sources')
def list_sources(project_id: str):
    return source_manifest(project_id)


@router.post('/api/projects/{project_id}/sources')
async def upload_source(project_id: str, file: UploadFile = File(...),
                        role: SourceRole = Form('other'), notes: str = Form('', max_length=2000)):
    directory = _directory(project_id)
    original = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    original = ''.join(char for char in original if char.isprintable()).strip()[:255]
    suffix = Path(original).suffix.lower()
    if suffix not in FORMATS:
        raise HTTPException(400, 'Upload a PDF, PNG, JPEG, WebP, or TIFF supporting source')
    if len(_entries(directory)) >= MAX_FILES:
        raise HTTPException(409, 'A project can have up to 20 supporting sources')
    directory.mkdir(exist_ok=True)
    identifier = uuid.uuid4().hex
    destination = directory / (identifier + suffix)
    temporary = directory / (identifier + '.part')
    digest = hashlib.sha256()
    size = 0
    committed = False
    try:
        with temporary.open('xb') as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'Use a supporting source smaller than 200 MB')
                digest.update(chunk)
                output.write(chunk)
        if not size:
            raise HTTPException(400, 'The upload is empty')
        _validate_source(temporary, suffix)
        entry = {'id': identifier, 'original_name': original, 'filename': destination.name,
                 'sha256': digest.hexdigest(), 'size_bytes': size, 'media_type': FORMATS[suffix],
                 'role': role, 'notes': notes, 'status': STATUS,
                 'uploaded_at': datetime.now(timezone.utc).isoformat(),
                 'download_url': f'/api/projects/{project_id}/sources/{identifier}'}
        with (directory / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            entries = _entries(directory)
            if len(entries) >= MAX_FILES:
                raise HTTPException(409, 'A project can have up to 20 supporting sources')
            temporary.replace(destination)
            entries.append(entry)
            index = directory / 'index.tmp'
            index.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
            index.replace(directory / 'index.json')
            committed = True
        return {'project_id': project_id, 'sources': entries}
    finally:
        temporary.unlink(missing_ok=True)
        if not committed:
            destination.unlink(missing_ok=True)
        await file.close()


@router.get('/api/projects/{project_id}/sources/{source_id}')
def download_source(project_id: str, source_id: str):
    directory = _directory(project_id)
    if not re.fullmatch(r'[0-9a-f]{32}', source_id):
        raise HTTPException(404, 'Source not found')
    entry = next((entry for entry in _entries(directory) if entry.get('id') == source_id), None)
    if not entry:
        raise HTTPException(404, 'Source not found')
    filename = entry.get('filename', '')
    path = directory / filename
    if (Path(filename).stem != source_id or Path(filename).suffix not in FORMATS
            or path.resolve().parent != directory.resolve() or not path.is_file()):
        raise HTTPException(404, 'Source not found')
    return FileResponse(path, media_type=entry['media_type'], filename=entry['original_name'],
                        headers={'X-Content-Type-Options': 'nosniff'})
