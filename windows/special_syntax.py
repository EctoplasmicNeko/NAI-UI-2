from PySide6.QtWidgets import QDialog, QGridLayout, QPushButton, QTextBrowser


# Keep in sync with the prompt processing in process/process_generate.py.
SPECIAL_SYNTAX_HTML = """
<h2>Prompt Special Syntax</h2>

<h3>Separating tags</h3>
<p>Tags are separated by commas. A new line also counts as a comma.</p>

<h3>Weights (NovelAI)</h3>
<p><code>1.5::tag::</code> &mdash; strengthens a tag. Use a value below 1, or a negative value, to weaken or invert it.<br>
Weights are kept when a tag is substituted, gender-swapped or checked against outfit removals.</p>

<h3>Random weights</h3>
<p><code>!tag!0.5!1.5!</code> &mdash; chooses a random strength between the two values for each generation,
then rounds it to one decimal place, for example <code>0.9::tag::</code>.<br>
The syntax stays unchanged in prompt previews and saved prompts. Tag associations, outfit removals,
substitutions and gender swaps run before random weights are resolved, so they do not recognize the enclosed tag.</p>

<h3>Text</h3>
<p><code>text: something</code> or <code>"something"</code> &mdash; marks a text tag.<br>
Text tags are always moved to the end of the prompt, and duplicates are removed.<br>
Commas inside double quotes do not split the tag:
<code>text: "I came, I saw, I won"</code> becomes <code>text: I came, I saw, I won</code>.<br>
The scramble modifiers keep text tags at the end.</p>

<h3>Wildcards</h3>
<p><code>*name*</code> &mdash; replaced with a random (weighted) entry from the wildcard called <i>name</i>
(see Manage Wildcards / <code>user_config/wildcards/name.json</code>).<br>
Can be part of a larger tag, e.g. <code>*colour* dress</code>. A wildcard entry can itself contain wildcards.<br>
Unknown wildcard names are left as they are.</p>

<h3>Character name</h3>
<p><code>&amp;c1&amp;</code> &mdash; replaced with the name of the character in slot 1 (<code>c1</code> to <code>c5</code>).<br>
Can be part of a larger tag, e.g. <code>&amp;c1&amp; (cosplay)</code>.<br>
Only applies to the base (global) positive prompt.</p>

<h3>Conditional insert</h3>
<p><code>$c1$trigger$tags$</code> &mdash; inserts <i>tags</i> only if the character in slot 1 has the character tag <i>trigger</i>.
Otherwise the whole entry is removed.<br>
The inserted part may contain commas, e.g. <code>$c1$male$shorts, underwear peek$, $c1$female$panties, skirt$</code>.</p>

<h3>Slot substitution</h3>
<p><code>?c1?tag?</code> &mdash; looks up substitution rules for <i>tag</i> in <code>user_config/substitutions</code>.
If the character in slot 1 has one of a rule's trigger tags, <i>tag</i> is replaced with that rule's substitute.
Otherwise <i>tag</i> is used unchanged.<br>
Weights are kept: <code>?c1?1.2::boy::?</code>.</p>

<h3>Guarded tags</h3>
<p><code>#tag#</code> &mdash; hides the tag from tag associations and outfit removal lists, so it won't trigger or be removed by them.
The <code>#</code> markers are stripped from the final prompt.</p>
"""


class SpecialSyntaxDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Special Syntax")
        self.resize(560, 640)

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenLinks(False)
        self.text_browser.setHtml(SPECIAL_SYNTAX_HTML)
        self.grid.addWidget(self.text_browser, 0, 0)

        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.close)
        self.grid.addWidget(self.close_button, 1, 0)
