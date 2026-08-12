"""Script validation — EP1-shaped failures and keyword parsing."""

from __future__ import annotations

from src.agents.crews.batch_validate import normalize_script_dict, validate_script_dict
from src.book_queue.models import ScriptOutput
from src.hashtags.brand import normalize_brand_hashtag
from src.script_gen.limits import script_char_limits
from src.config import AppConfig


STYLE = "noir lighting, teal-blue color grade, cinematic"
BRAND = "#RahasyaExe"


def _base(**overrides) -> dict:
    body = (
        "Police ने वो file देखी… और face से colour उड़ गया। "
        "वॉल्टर को सिर्फ एक warning मिली थी — Limmeridge से दूर रहना। "
        "लेकिन वो warning देने वाली औरत सफ़ेद dress में रात के अँधेरे में गायब हो गई। "
        "अब उसके पास सिर्फ एक नाम है। कोई proof नहीं। कोई witness नहीं। "
        "क्या वो warning झूठ थी या कोई plan पहले से चल रहा है? "
    )
    # Pad to clear 75*10 = 750 min for default config
    while len(body) < 760:
        body += "तनाव और बढ़ रहा है। हर कदम पर नया खतरा। "
    data = {
        "voiceover_script": body,
        "episode_only_script": body,
        "english_voiceover": "Police saw the file — and the colour drained from his face.",
        "hook": "Police saw the file",
        "cliffhanger": "Was the warning a lie?",
        "caption_hook": "वो warning झूठ थी?",
        "caption_teaser": "क्या Limmeridge का राज़ उसे निगल जाएगा?",
        "static_post_text": "Police ने file देखी #RahasyaExe",
        "stock_keywords": ["victorian london street", "woman in white dress", STYLE],
        "on_screen_text": ["Police ने file देखी…"],
        "english_on_screen": ["Police saw the file…"],
    }
    data.update(overrides)
    return data


def test_ep1_banned_opening_fails() -> None:
    data = _base(
        voiceover_script="एक दिन वॉल्टर लंदन की सड़क पर चल रहा था। " + ("x" * 700),
        episode_only_script="",
    )
    data["episode_only_script"] = data["voiceover_script"]
    err = validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND)
    assert err and "banned opening" in err


def test_ep1_mood_only_keywords_fail() -> None:
    data = _base(stock_keywords=["cinematic", "dark", "mystery"])
    err = validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND)
    assert err and "stock_keywords" in err


def test_ep1_generic_onscreen_fails() -> None:
    data = _base(on_screen_text=["एक रहस्यमयी मुलाकात"])
    err = validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND)
    assert err and "generic on_screen_text" in err


def test_ep1_missing_caption_question_fails() -> None:
    data = _base(caption_hook="एक रहस्य शुरू होता है", caption_teaser="अगला भाग जल्द")
    err = validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND)
    assert err and "plot question" in err


def test_ep1_typo_hashtag_fails() -> None:
    data = _base(static_post_text="hook text #rahaysaexe")
    err = validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND)
    assert err and "hashtag" in err


def test_good_script_passes() -> None:
    data = _base()
    assert validate_script_dict(data, 700, 900, style_tag=STYLE, brand_hashtag=BRAND) is None


def test_keyword_string_splits_on_commas() -> None:
    keywords = ScriptOutput._coerce_keywords(
        "victorian london street, woman in white, cinematic"
    )
    assert keywords == ["victorian london street", "woman in white", "cinematic"]
    # Must not char-iterate
    assert len(keywords) == 3


def test_from_dict_no_mood_default() -> None:
    script = ScriptOutput.from_dict(
        {
            "voiceover_script": "Police ने देखा।",
            "stock_keywords": "",
            "on_screen_text": ["Police ने देखा"],
        }
    )
    assert script.stock_keywords == []


def test_normalize_injects_style_tag() -> None:
    data = normalize_script_dict(
        _base(stock_keywords=["victorian london", "woman in white"]),
        900,
        style_tag=STYLE,
    )
    assert any("noir" in k.lower() or "teal" in k.lower() for k in data["stock_keywords"])


def test_brand_hashtag_rewrites_typo() -> None:
    text, found = normalize_brand_hashtag(
        "#thrillerbooks #rahaysaexe #booktok", "#RahasyaExe"
    )
    assert found
    assert "#RahasyaExe" in text
    assert "#rahaysaexe" not in text.lower() or "#RahasyaExe" in text


def test_char_density_raised() -> None:
    cfg = AppConfig(script_min_seconds=75, script_max_seconds=80)
    mn, mx = script_char_limits(cfg)
    assert mn == 750
    assert mx == 880
