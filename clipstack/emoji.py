"""Emoji & symbols tab for the popup.

A small built-in list (no downloads, no extra packages). Each entry has
search keywords; the popup's search box filters this tab too.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

# (character, keywords). Grouped by category; the category name is added to
# the keywords so that e.g. "arrow" or "math" finds the whole group.
_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("smiley face", [
        ("😀", "grinning happy"), ("😃", "smile happy"), ("😄", "smile laugh"),
        ("😁", "grin beaming"), ("😆", "laughing"), ("😅", "sweat smile"),
        ("🤣", "rofl rolling laughing"), ("😂", "joy tears laughing"),
        ("🙂", "slight smile"), ("🙃", "upside down"), ("😉", "wink"),
        ("😊", "blush smile"), ("😇", "innocent halo angel"), ("🥰", "love hearts"),
        ("😍", "heart eyes love"), ("🤩", "star struck"), ("😘", "kiss blow"),
        ("😋", "yum tasty"), ("😛", "tongue"), ("😜", "wink tongue crazy"),
        ("🤪", "zany crazy"), ("🤔", "thinking hmm"), ("🤨", "raised eyebrow"),
        ("😐", "neutral"), ("😑", "expressionless"), ("😶", "no mouth"),
        ("🙄", "eye roll"), ("😏", "smirk"), ("😬", "grimace awkward"),
        ("😌", "relieved"), ("😔", "pensive sad"), ("😴", "sleeping zzz"),
        ("😷", "mask sick"), ("🤒", "fever sick thermometer"), ("🤯", "mind blown exploding"),
        ("🥳", "party celebrate"), ("😎", "cool sunglasses"), ("🤓", "nerd glasses"),
        ("😕", "confused"), ("😟", "worried"), ("😮", "open mouth surprised"),
        ("😲", "astonished shocked"), ("😳", "flushed embarrassed"), ("🥺", "pleading puppy eyes"),
        ("😢", "cry sad tear"), ("😭", "sob crying loud"), ("😱", "scream fear"),
        ("😤", "triumph huff"), ("😡", "angry pouting rage"), ("🤬", "cursing swearing"),
        ("😈", "devil smiling"), ("💀", "skull dead"), ("💩", "poop"),
        ("🤡", "clown"), ("👻", "ghost"), ("👽", "alien"), ("🤖", "robot"),
        ("🙈", "see no evil monkey"), ("🙉", "hear no evil monkey"), ("🙊", "speak no evil monkey"),
    ]),
    ("hand gesture people", [
        ("👍", "thumbs up like yes ok"), ("👎", "thumbs down dislike no"),
        ("👌", "ok perfect"), ("✌️", "victory peace"), ("🤞", "fingers crossed luck"),
        ("🤟", "love you"), ("🤘", "rock horns"), ("🤙", "call me shaka"),
        ("👈", "point left"), ("👉", "point right"), ("👆", "point up"),
        ("👇", "point down"), ("☝️", "index up"), ("✋", "raised hand stop"),
        ("👋", "wave hello bye"), ("👏", "clap applause"), ("🙌", "raising hands hooray"),
        ("👐", "open hands"), ("🤲", "palms up"), ("🙏", "pray thanks please folded"),
        ("🤝", "handshake deal"), ("💪", "muscle strong flex"), ("✍️", "writing"),
        ("👀", "eyes look"), ("🧠", "brain smart"), ("🫶", "heart hands"),
        ("🤷", "shrug dunno"), ("🤦", "facepalm"), ("🙋", "raising hand"),
        ("🙆", "ok gesture"), ("🙅", "no gesture"), ("💁", "tipping hand"),
    ]),
    ("symbol", [
        ("❤️", "red heart love"), ("🧡", "orange heart"), ("💛", "yellow heart"),
        ("💚", "green heart"), ("💙", "blue heart"), ("💜", "purple heart"),
        ("🖤", "black heart"), ("🤍", "white heart"), ("🤎", "brown heart"),
        ("💔", "broken heart"), ("💕", "two hearts"), ("💖", "sparkling heart"),
        ("💯", "hundred 100 perfect"), ("💥", "boom collision"), ("💫", "dizzy"),
        ("💬", "speech bubble"), ("💭", "thought bubble"), ("💤", "zzz sleep"),
        ("✨", "sparkles"), ("⭐", "star"), ("🌟", "glowing star"), ("🔥", "fire hot lit"),
        ("⚡", "lightning zap"), ("🎉", "party popper tada"), ("🎊", "confetti"),
        ("✅", "check mark done yes"), ("❌", "cross mark no wrong"), ("❗", "exclamation"),
        ("❓", "question"), ("⚠️", "warning"), ("🚫", "prohibited forbidden"),
        ("⛔", "no entry"), ("🔴", "red circle"), ("🟢", "green circle"),
        ("🟡", "yellow circle"), ("🔵", "blue circle"), ("⚪", "white circle"),
        ("⚫", "black circle"), ("🆗", "ok button"), ("🆕", "new button"),
    ]),
    ("animal nature weather", [
        ("🐶", "dog puppy"), ("🐱", "cat kitten"), ("🐭", "mouse"), ("🐰", "rabbit bunny"),
        ("🦊", "fox"), ("🐻", "bear"), ("🐼", "panda"), ("🐨", "koala"),
        ("🐯", "tiger"), ("🦁", "lion"), ("🐮", "cow"), ("🐷", "pig"),
        ("🐸", "frog"), ("🐵", "monkey"), ("🐔", "chicken"), ("🐧", "penguin linux tux"),
        ("🐦", "bird"), ("🦄", "unicorn"), ("🐝", "bee"), ("🦋", "butterfly"),
        ("🐢", "turtle"), ("🐍", "snake"), ("🐙", "octopus"), ("🐬", "dolphin"),
        ("🐳", "whale"), ("🌸", "cherry blossom flower"), ("🌹", "rose flower"),
        ("🌻", "sunflower"), ("🌳", "tree"), ("🌵", "cactus"), ("🍀", "four leaf clover luck"),
        ("🍁", "maple leaf autumn"), ("☀️", "sun sunny"), ("🌙", "moon night"),
        ("☁️", "cloud"), ("🌧️", "rain"), ("⛈️", "storm thunder"), ("❄️", "snowflake cold"),
        ("🌈", "rainbow"), ("🌊", "wave ocean sea"), ("🌍", "earth globe world"),
    ]),
    ("food drink", [
        ("🍎", "apple red"), ("🍌", "banana"), ("🍇", "grapes"), ("🍓", "strawberry"),
        ("🍉", "watermelon"), ("🍊", "orange tangerine"), ("🍋", "lemon"), ("🍑", "peach"),
        ("🥑", "avocado"), ("🍅", "tomato"), ("🥕", "carrot"), ("🌽", "corn"),
        ("🍞", "bread"), ("🧀", "cheese"), ("🍳", "egg cooking"), ("🍔", "burger hamburger"),
        ("🍟", "fries"), ("🍕", "pizza"), ("🌭", "hot dog"), ("🌮", "taco"),
        ("🍣", "sushi"), ("🍜", "ramen noodles"), ("🍩", "donut doughnut"), ("🍪", "cookie"),
        ("🎂", "birthday cake"), ("🍰", "cake slice"), ("🍫", "chocolate"), ("🍿", "popcorn"),
        ("☕", "coffee hot"), ("🍵", "tea"), ("🍺", "beer"), ("🍷", "wine"),
        ("🥂", "cheers toast champagne"), ("🥤", "soda cup"), ("💧", "water drop"),
    ]),
    ("object activity travel", [
        ("💻", "laptop computer"), ("🖥️", "desktop computer"), ("⌨️", "keyboard"),
        ("🖱️", "mouse computer"), ("📱", "phone mobile"), ("📷", "camera"),
        ("🎧", "headphones music"), ("🎵", "music note"), ("🎮", "game controller"),
        ("📚", "books"), ("📖", "book open"), ("📝", "memo note"), ("✏️", "pencil"),
        ("📌", "pushpin pin"), ("📎", "paperclip"), ("📅", "calendar"), ("⏰", "alarm clock"),
        ("⌛", "hourglass"), ("💡", "bulb idea"), ("🔑", "key"), ("🔒", "lock locked"),
        ("🔓", "unlock"), ("🔔", "bell"), ("📢", "loudspeaker announce"), ("📦", "package box"),
        ("✉️", "envelope mail"), ("📧", "email"), ("🔗", "link chain"), ("🔍", "search magnifier"),
        ("🛠️", "tools hammer wrench"), ("⚙️", "gear settings"), ("🧪", "test tube"),
        ("💰", "money bag"), ("💳", "credit card"), ("🎁", "gift present"), ("🏆", "trophy"),
        ("⚽", "soccer football"), ("🏀", "basketball"), ("🚀", "rocket launch"),
        ("✈️", "airplane"), ("🚗", "car"), ("🚲", "bicycle"), ("🏠", "house home"),
    ]),
    ("arrow", [
        ("←", "left"), ("→", "right"), ("↑", "up"), ("↓", "down"), ("↔", "left right"),
        ("↕", "up down"), ("⇐", "double left"), ("⇒", "double right implies"),
        ("⇔", "double left right iff"), ("↩", "return back"), ("↪", "forward"),
        ("⟵", "long left"), ("⟶", "long right"), ("➜", "heavy right"),
        ("⬅️", "left emoji"), ("➡️", "right emoji"), ("⬆️", "up emoji"), ("⬇️", "down emoji"),
        ("🔄", "refresh reload counterclockwise"), ("🔁", "repeat loop"),
    ]),
    ("math", [
        ("±", "plus minus"), ("×", "times multiply"), ("÷", "divide division"),
        ("≈", "approximately almost equal"), ("≠", "not equal"), ("≤", "less equal"),
        ("≥", "greater equal"), ("∞", "infinity"), ("√", "square root"),
        ("∑", "sum sigma"), ("∏", "product pi"), ("∫", "integral"), ("∂", "partial"),
        ("∆", "delta increment"), ("∇", "nabla"), ("π", "pi"), ("µ", "micro mu"),
        ("°", "degree"), ("‰", "per mille"), ("¹", "superscript one"), ("²", "squared superscript two"),
        ("³", "cubed superscript three"), ("½", "half"), ("¼", "quarter"), ("¾", "three quarters"),
        ("∈", "element of in"), ("∉", "not element"), ("∩", "intersection"), ("∪", "union"),
        ("⊂", "subset"), ("∀", "for all"), ("∃", "exists"), ("¬", "not"),
        ("∧", "and logical"), ("∨", "or logical"), ("α", "alpha"), ("β", "beta"),
        ("γ", "gamma"), ("λ", "lambda"), ("θ", "theta"), ("σ", "sigma small"),
        ("Ω", "omega ohm"),
    ]),
    ("currency money", [
        ("€", "euro"), ("£", "pound sterling"), ("¥", "yen yuan"), ("$", "dollar"),
        ("¢", "cent"), ("₹", "rupee india"), ("₽", "ruble"), ("₩", "won korea"),
        ("₺", "lira turkey"), ("₴", "hryvnia"), ("₸", "tenge kazakhstan"), ("₿", "bitcoin"),
        ("₦", "naira"), ("₱", "peso"), ("₫", "dong"),
    ]),
    ("punctuation typography", [
        ("—", "em dash"), ("–", "en dash"), ("…", "ellipsis dots"), ("•", "bullet"),
        ("·", "middle dot"), ("«", "guillemet left quote"), ("»", "guillemet right quote"),
        ("“", "left double quote"), ("”", "right double quote"), ("‘", "left single quote"),
        ("’", "right single quote apostrophe"), ("„", "low double quote"),
        ("¿", "inverted question"), ("¡", "inverted exclamation"), ("§", "section"),
        ("¶", "pilcrow paragraph"), ("†", "dagger"), ("‡", "double dagger"),
        ("©", "copyright"), ("®", "registered"), ("™", "trademark"), ("№", "numero number"),
        ("✓", "check tick"), ("✗", "ballot x cross"), ("★", "star black"), ("☆", "star white"),
        ("♥", "heart suit"), ("♦", "diamond suit"), ("♣", "club suit"), ("♠", "spade suit"),
        ("♪", "eighth note music"), ("☺", "smiley white"), ("☐", "ballot box"),
        ("☑", "ballot box check"), ("⌘", "command mac"), ("⌥", "option alt mac"),
        ("⇧", "shift"), ("⌫", "backspace erase"), ("⏎", "return enter"), ("␣", "space"),
    ]),
]

EMOJI: list[tuple[str, str]] = [
    (char, f"{words} {category}") for category, items in _GROUPS for char, words in items
]


def matches(keywords: str, query: str) -> bool:
    """True if every word of ``query`` starts a word in ``keywords``."""
    words = keywords.casefold().split()
    return all(any(w.startswith(q) for w in words) for q in query.casefold().split())


class EmojiPage(Gtk.ScrolledWindow):
    """A grid of emoji/symbol buttons. ``on_pick(text)`` is called on click/Enter."""

    def __init__(self, on_pick: Callable[[str], None]) -> None:
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._query = ""
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flow.set_activate_on_single_click(True)
        self.flow.set_homogeneous(True)
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_max_children_per_line(10)
        self.flow.set_min_children_per_line(6)
        self.flow.get_style_context().add_class("clipstack-emoji")
        for char, keywords in EMOJI:
            label = Gtk.Label(label=char)
            child = Gtk.FlowBoxChild()
            child.add(label)
            child.set_tooltip_text(keywords.split()[0] if keywords else char)
            child.keywords = keywords  # type: ignore[attr-defined]
            child.char = char  # type: ignore[attr-defined]
            self.flow.add(child)
        self.flow.set_filter_func(lambda c: matches(c.keywords, self._query))
        self.flow.connect("child-activated", lambda _f, c: on_pick(c.char))
        self.add(self.flow)

    def filter(self, query: str) -> None:
        self._query = query.strip()
        self.flow.invalidate_filter()

    def focus_first(self) -> None:
        for child in self.flow.get_children():
            if child.get_child_visible() and child.get_mapped():
                self.flow.select_child(child)
                child.grab_focus()
                return
