import os

from fastapi import HTTPException, UploadFile, status

CHUNK_SIZE = 1024 * 1024
if "HTTP_413_CONTENT_TOO_LARGE" in dir(status):
    HTTP_413_CONTENT_TOO_LARGE = status.HTTP_413_CONTENT_TOO_LARGE
else:
    HTTP_413_CONTENT_TOO_LARGE = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


async def save_upload_file(
    upload: UploadFile,
    dest_path: str,
    max_bytes: int,
    *,
    enforce_pdf_header: bool = False,
) -> int:
    size = 0
    has_data = False
    first_chunk = True
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        with open(dest_path, "wb") as out_file:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                has_data = True
                if first_chunk and enforce_pdf_header:
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid PDF file",
                        )
                    first_chunk = False
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds {max_bytes // (1024 * 1024)}MB limit",
                    )
                out_file.write(chunk)
    except HTTPException:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise

    if enforce_pdf_header and not has_data:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty PDF file",
        )

    return size
