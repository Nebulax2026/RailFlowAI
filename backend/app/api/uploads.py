from collections.abc import Iterable
from pathlib import Path

from fastapi import HTTPException, UploadFile


MAX_IMPORT_BYTES = 1_000_000


async def read_upload_text(
    file: UploadFile,
    *,
    allowed_content_types: Iterable[str],
    allowed_extensions: Iterable[str],
) -> str:
    content_type = (file.content_type or "").split(";")[0].lower()
    allowed_types = {item.lower() for item in allowed_content_types}
    if content_type and content_type not in allowed_types:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {file.content_type}.")

    extension = Path(file.filename or "").suffix.lower()
    allowed_suffixes = {item.lower() for item in allowed_extensions}
    if extension and extension not in allowed_suffixes:
        raise HTTPException(status_code=415, detail=f"Unsupported file extension: {extension}.")

    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Import file is too large.")

    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="Import file must be UTF-8 encoded.") from error
