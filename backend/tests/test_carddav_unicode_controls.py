from services.carddav_discovery import _txt_context_path


def test_txt_context_path_rejects_unicode_c1_control():
    assert _txt_context_path(["path=/safe%C2%85header"]) is None
