# Signature file dicek langsung karena ekstensi/content-type dari DMS tidak selalu sesuai isi file.
_IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}


class UnsupportedImageError(ValueError):
    pass


def detect_image_type(content: bytes) -> tuple[str, str]:
    """Kembalikan (content_type, ekstensi) berdasarkan isi file."""
    for signature, image_type in _IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            return image_type
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise UnsupportedImageError("File bukan JPEG, PNG, atau WebP")
