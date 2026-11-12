import json

from app import videopipeline


def test_storyboard_parser_accepts_json_with_prose_and_ignores_trailing_object():
    first = {"các_cảnh": [{"stt": 1}], "model_used": "x"}
    text = "Here is the result:\n" + json.dumps(first, ensure_ascii=False) + '\nNote: {"not": "storyboard"}'
    assert videopipeline._parse_storyboard_json(text) == first


def test_storyboard_parser_rejects_non_object():
    try:
        videopipeline._parse_storyboard_json("not json")
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("invalid JSON should be rejected")


def test_extract_storyboard_text_supports_content_blocks():
    message = {"content": [{"type": "text", "text": '{"các_cảnh": []}'}]}
    assert videopipeline._extract_storyboard_text(message) == '{"các_cảnh": []}'


def test_extract_storyboard_text_supports_structured_content():
    message = {"content": {"json": {"các_cảnh": []}}}
    assert videopipeline._extract_storyboard_text(message) == '{"các_cảnh": []}'
