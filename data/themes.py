import json
import re

from data.paths import THEMES_DIR


THEME_TEMPLATE_FILE = THEMES_DIR / "template.qss"
THEME_PALETTES_FILE = THEMES_DIR / "palettes.json"
THEME_TOKEN_PATTERN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
COLOR_VALUE_PATTERN = re.compile(
    r"(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}"
    r"|rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,"
    r"\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\s*\))"
)


def _load_template() -> str:
    return THEME_TEMPLATE_FILE.read_text(encoding="utf-8")


def load_theme_palettes() -> dict[str, dict[str, str]]:
    palettes = json.loads(THEME_PALETTES_FILE.read_text(encoding="utf-8"))
    if not isinstance(palettes, dict) or not palettes:
        raise ValueError("Theme palettes must be a non-empty object.")

    required_tokens = set(THEME_TOKEN_PATTERN.findall(_load_template()))
    if not required_tokens:
        raise ValueError("Theme template does not contain any color tokens.")

    for theme_name, palette in palettes.items():
        if not isinstance(theme_name, str) or not isinstance(palette, dict):
            raise ValueError("Each theme must map a name to a color palette.")

        palette_tokens = set(palette)
        if palette_tokens != required_tokens:
            missing = sorted(required_tokens - palette_tokens)
            extra = sorted(palette_tokens - required_tokens)
            raise ValueError(
                f"Theme '{theme_name}' has invalid color roles; "
                f"missing={missing}, extra={extra}."
            )

        for role, color in palette.items():
            if not isinstance(color, str) or COLOR_VALUE_PATTERN.fullmatch(color) is None:
                raise ValueError(
                    f"Theme '{theme_name}' role '{role}' is not a supported color: {color!r}."
                )

    return palettes


def available_themes() -> list[str]:
    return sorted(load_theme_palettes())


def render_theme(theme_name: str) -> str:
    template = _load_template()
    palettes = load_theme_palettes()
    if theme_name not in palettes:
        raise ValueError(f"Unknown theme: {theme_name!r}.")

    palette = palettes[theme_name]
    rendered = THEME_TOKEN_PATTERN.sub(
        lambda match: palette[match.group(1)],
        template,
    )
    if THEME_TOKEN_PATTERN.search(rendered) is not None:
        raise ValueError(f"Theme '{theme_name}' left unresolved color tokens.")
    return rendered