from app.clients import minio_storage


def test_content_type_from_object_name() -> None:
    assert minio_storage._content_type_from_object_name("task-images/demo.png") == "image/png"
    assert minio_storage._content_type_from_object_name("task-images/demo.jpg") == "image/jpeg"
    assert minio_storage._content_type_from_object_name("task-images/demo.webp") == "image/webp"
    assert minio_storage._content_type_from_object_name("attachments/demo.pdf") == "application/pdf"
    assert minio_storage._content_type_from_object_name("attachments/demo.docx").startswith("application/vnd.openxmlformats")


def test_unknown_content_type_falls_back_to_octet_stream() -> None:
    assert minio_storage._content_type_from_object_name("task-images/demo.bin") == "application/octet-stream"


def test_safe_filename_normalizes_untrusted_names() -> None:
    assert minio_storage._safe_filename("../My File?.pdf", "pdf") == "My-File.pdf"
    assert minio_storage._safe_filename("", "png") == "attachment.png"


def test_validate_object_name_rejects_path_traversal() -> None:
    minio_storage._validate_object_name("attachments/demo.pdf", prefixes={"attachments"})
    try:
        minio_storage._validate_object_name("attachments/../secret.pdf", prefixes={"attachments"})
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal should be rejected")
