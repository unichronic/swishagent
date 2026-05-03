import base64
import io

from PIL import Image

import tools


def test_load_photo_bytes_accepts_data_url():
    image = Image.new("RGB", (8, 8), (20, 120, 60))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")

    payload, mime_type = tools._load_photo_bytes(f"data:image/png;base64,{encoded}")

    assert mime_type == "image/png"
    assert payload == buf.getvalue()
