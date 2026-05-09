from app.clients import minio_storage


def test_content_type_from_object_name() -> None:
    assert minio_storage._content_type_from_object_name("task-images/demo.png") == "image/png"
    assert minio_storage._content_type_from_object_name("task-images/demo.jpg") == "image/jpeg"
    assert minio_storage._content_type_from_object_name("task-images/demo.webp") == "image/webp"


def test_unknown_content_type_falls_back_to_octet_stream() -> None:
    assert minio_storage._content_type_from_object_name("task-images/demo.bin") == "application/octet-stream"
