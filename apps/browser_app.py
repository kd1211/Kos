"""
Browser -- a minimal text-only web browser with tabs and editable bookmarks.

Bookmarks are persisted to ~/.pios_bookmarks.json (seeded from DEFAULT_BOOKMARKS
the first time the app runs) so adds/edits/deletes survive a reboot.

Tabs: up to MAX_TABS independent browsing contexts, each with its own
bookmarks-or-page state, switchable from a small tab strip under the
status bar. Closing the last tab reopens a fresh blank one.
"""

import os
import re
import json
import textwrap
from html.parser import HTMLParser
from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT, FG_COLOR

DEFAULT_BOOKMARKS = [
    {"title": "Example.com", "url": "https://example.com"},
    {"title": "Anthropic", "url": "https://www.anthropic.com"},
    {"title": "Wikipedia (random)", "url": "https://en.wikipedia.org/wiki/Special:Random"},
    {"title": "Hacker News", "url": "https://news.ycombinator.com"},
]

BOOKMARKS_PATH = os.path.expanduser("~/.pios_bookmarks.json")

LINES_PER_PAGE = 15
CHARS_PER_LINE = 38
KEYBOARD_H = 188
MAX_URL_LEN = 60
MAX_TITLE_LEN = 24

TAB_BAR_H = 30
MAX_TABS = 4
CONTENT_TOP = STATUS_BAR_H + TAB_BAR_H


def load_bookmarks():
    try:
        with open(BOOKMARKS_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            return [b for b in data if "title" in b and "url" in b]
    except Exception:
        pass
    return [dict(b) for b in DEFAULT_BOOKMARKS]


def save_bookmarks(bookmarks):
    try:
        with open(BOOKMARKS_PATH, "w") as f:
            json.dump(bookmarks, f)
    except Exception:
        pass


class _TextExtractor(HTMLParser):
    """Very small HTML-to-text stripper: skips script/style, keeps the rest."""

    def __init__(self):
        super().__init__()
        self.chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.chunks.append(text)

    def get_text(self):
        return "\n".join(self.chunks)


def _new_tab():
    return {"pages": [], "page_index": 0, "title": None, "url": None}


class BrowserApp(App):
    name = "Browser"
    icon = "\U0001F310"

    def on_open(self):
        self.bookmarks = load_bookmarks()
        self.tabs = [_new_tab()]
        self.active = 0
        self.mode = "browse"      # browse | type | bm_edit
        self.status = None
        self.keyboard = None
        self.draft_url = ""
        self.bm_edit = None       # {"idx": i or None, "field": "title"/"url", "title":.., "url":..}
        self._rebuild()

    # -- tab helpers ------------------------------------------------------
    @property
    def tab(self):
        return self.tabs[self.active]

    def _select_tab(self, i):
        self.active = i
        self.mode = "browse"
        self._rebuild()

    def _close_tab(self, i):
        del self.tabs[i]
        if not self.tabs:
            self.tabs = [_new_tab()]
            self.active = 0
        else:
            self.active = min(i, len(self.tabs) - 1)
        self.mode = "browse"
        self._rebuild()

    def _add_tab(self):
        if len(self.tabs) >= MAX_TABS:
            self.status = "Tab limit reached"
            return
        self.tabs.append(_new_tab())
        self.active = len(self.tabs) - 1
        self.mode = "browse"
        self._rebuild()

    # -- building all buttons (tab strip + content) ------------------------
    def _rebuild(self):
        self.buttons = []
        self._build_tab_strip()
        if self.mode == "type":
            self._build_type_buttons()
        elif self.mode == "bm_edit":
            self._build_bm_edit_buttons()
        elif self.tab["pages"]:
            self._build_page_buttons()
        else:
            self._build_bookmark_buttons()

    def _build_tab_strip(self):
        n = len(self.tabs)
        plus_w = 30
        tab_w = (SCREEN_W - plus_w) // n
        for i in range(n):
            x = i * tab_w
            # close hitbox (checked first so it wins over the select area)
            if n > 1:
                self.buttons.append(
                    Button(x + tab_w - 22, STATUS_BAR_H, 22, TAB_BAR_H, "\u2715",
                           (lambda i=i: self._close_tab(i)), font=FONT_SM))
            self.buttons.append(
                Button(x, STATUS_BAR_H, tab_w, TAB_BAR_H, "",
                       (lambda i=i: self._select_tab(i)), font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W - plus_w, STATUS_BAR_H, plus_w, TAB_BAR_H, "+",
                   self._add_tab, font=FONT_MD))

    # -- bookmarks list -----------------------------------------------------
    def _build_bookmark_buttons(self):
        top = CONTENT_TOP + 44
        row_h = 42
        for i, b in enumerate(self.bookmarks):
            y = top + i * row_h
            if y > SCREEN_H - 130:
                break
            self.buttons.append(
                Button(16, y, SCREEN_W - 74, row_h - 6, b["title"],
                       self._open_url(b["title"], b["url"]), font=FONT_SM))
            self.buttons.append(
                Button(SCREEN_W - 54, y, 40, row_h - 6, "\u270E",
                       (lambda i=i: self._start_edit_bookmark(i)), font=FONT_SM))

        bottom = SCREEN_H - 110
        self.buttons.append(
            Button(16, bottom, SCREEN_W - 32, 40, "Type a URL...", self._start_typing, font=FONT_SM))
        self.buttons.append(
            Button(16, bottom + 48, (SCREEN_W - 40) // 2, 40, "+ Bookmark",
                   self._start_add_bookmark, font=FONT_SM))
        self.buttons.append(
            Button(24 + (SCREEN_W - 40) // 2, bottom + 48, (SCREEN_W - 40) // 2, 40,
                   "Home", self.os.go_home, font=FONT_SM))

    def _open_url(self, title, url):
        def handler():
            self._fetch(title, url)
        return handler

    # -- typing a custom URL --------------------------------------------
    def _start_typing(self):
        self.mode = "type"
        self.draft_url = "https://"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _build_type_buttons(self):
        self.buttons.append(
            Button(16, CONTENT_TOP + 92, 90, 34, "Cancel", self._cancel_typing, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W - 106, CONTENT_TOP + 92, 90, 34, "Go", self._go_to_draft, font=FONT_SM))

    def _cancel_typing(self):
        self.mode = "browse"
        self._rebuild()

    def _go_to_draft(self):
        url = self.draft_url.strip()
        if url and url != "https://":
            self._fetch(url, url)
        else:
            self.mode = "browse"
            self._rebuild()

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft_url = self.draft_url[:-1]
        elif val == "ENTER":
            self._go_to_draft()
        elif len(self.draft_url) < MAX_URL_LEN:
            self.draft_url += val

    # -- add/edit bookmarks --------------------------------------------------
    def _start_add_bookmark(self):
        self.bm_edit = {"idx": None, "field": "title", "title": "", "url": "https://"}
        self.mode = "bm_edit"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _start_edit_bookmark(self, idx):
        b = self.bookmarks[idx]
        self.bm_edit = {"idx": idx, "field": "title", "title": b["title"], "url": b["url"]}
        self.mode = "bm_edit"
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._rebuild()

    def _build_bm_edit_buttons(self):
        y0 = CONTENT_TOP + 8
        self.buttons.append(
            Button(16, y0 + 30, SCREEN_W - 32, 34, "", self._focus_field("title"),
                   bg=(46, 46, 56) if self.bm_edit["field"] == "title" else CARD_COLOR, font=FONT_SM))
        self.buttons.append(
            Button(16, y0 + 72, SCREEN_W - 32, 34, "", self._focus_field("url"),
                   bg=(46, 46, 56) if self.bm_edit["field"] == "url" else CARD_COLOR, font=FONT_SM))
        by = y0 + 114
        self.buttons.append(Button(10, by, 70, 32, "Cancel", self._cancel_bm_edit, font=FONT_SM))
        if self.bm_edit["idx"] is not None:
            self.buttons.append(Button(86, by, 70, 32, "Delete", self._delete_bookmark, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 86, by, 76, 32, "Save", self._save_bookmark, font=FONT_SM))

    def _focus_field(self, field):
        def handler():
            self.bm_edit["field"] = field
            self._rebuild()
        return handler

    def _cancel_bm_edit(self):
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _delete_bookmark(self):
        idx = self.bm_edit["idx"]
        if idx is not None and 0 <= idx < len(self.bookmarks):
            del self.bookmarks[idx]
            save_bookmarks(self.bookmarks)
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _save_bookmark(self):
        title = self.bm_edit["title"].strip() or "Untitled"
        url = self.bm_edit["url"].strip() or "https://"
        idx = self.bm_edit["idx"]
        if idx is None:
            self.bookmarks.append({"title": title, "url": url})
        else:
            self.bookmarks[idx] = {"title": title, "url": url}
        save_bookmarks(self.bookmarks)
        self.bm_edit = None
        self.mode = "browse"
        self._rebuild()

    def _bm_on_key(self, val):
        field = self.bm_edit["field"]
        maxlen = MAX_TITLE_LEN if field == "title" else MAX_URL_LEN
        if val == "BACKSPACE":
            self.bm_edit[field] = self.bm_edit[field][:-1]
        elif val == "ENTER":
            pass
        elif len(self.bm_edit[field]) < maxlen:
            self.bm_edit[field] += val

    # -- tap dispatch --------------------------------------------------------
    def on_tap(self, x, y):
        if self.mode == "type" and self.keyboard.on_tap(x, y, self._on_key):
            return True
        if self.mode == "bm_edit" and self.keyboard.on_tap(x, y, self._bm_on_key):
            return True
        return super().on_tap(x, y)

    # -- fetching a page ------------------------------------------------------
    def _fetch(self, title, url):
        try:
            import requests
        except ImportError:
            self.status = "The 'requests' package isn't installed"
            return

        try:
            resp = requests.get(url, timeout=8, headers={"User-Agent": "PiOS/1.0"})
            resp.raise_for_status()
            extractor = _TextExtractor()
            extractor.feed(resp.text)
            text = extractor.get_text()
            text = re.sub(r"\n{2,}", "\n", text)

            wrapped = []
            for line in text.splitlines():
                wrapped.extend(textwrap.wrap(line, CHARS_PER_LINE) or [""])

            pages = [wrapped[i:i + LINES_PER_PAGE]
                     for i in range(0, len(wrapped), LINES_PER_PAGE)] or [[]]
            self.tab["pages"] = pages
            self.tab["page_index"] = 0
            self.tab["title"] = title
            self.tab["url"] = url
            self.mode = "browse"
            self._rebuild()
        except Exception as e:
            self.status = f"Couldn't load page: {e}"

    def _build_page_buttons(self):
        footer_y = SCREEN_H - 46
        self.buttons.append(Button(8, footer_y, 62, 36, "Marks", self._back_to_bookmarks, font=FONT_SM))
        self.buttons.append(Button(74, footer_y, 54, 36, "Prev", self._prev_page, font=FONT_SM))
        self.buttons.append(Button(132, footer_y, 54, 36, "Next", self._next_page, font=FONT_SM))
        self.buttons.append(Button(190, footer_y, 62, 36, "\u2606 Add", self._bookmark_current, font=FONT_SM))
        self.buttons.append(Button(256, footer_y, 56, 36, "Home", self.os.go_home, font=FONT_SM))

    def _back_to_bookmarks(self):
        self.mode = "browse"
        self._rebuild()

    def _prev_page(self):
        if self.tab["page_index"] > 0:
            self.tab["page_index"] -= 1

    def _next_page(self):
        if self.tab["page_index"] < len(self.tab["pages"]) - 1:
            self.tab["page_index"] += 1

    def _bookmark_current(self):
        title, url = self.tab["title"], self.tab["url"]
        if url and not any(b["url"] == url for b in self.bookmarks):
            self.bookmarks.append({"title": title or url, "url": url})
            save_bookmarks(self.bookmarks)
            self.status = "Bookmarked"
        else:
            self.status = "Already bookmarked"

    # -- drawing --------------------------------------------------------------
    def _draw_tab_strip(self, draw):
        n = len(self.tabs)
        plus_w = 30
        tab_w = (SCREEN_W - plus_w) // n
        for i, t in enumerate(self.tabs):
            x = i * tab_w
            active = (i == self.active)
            bg = ACCENT if active else CARD_COLOR
            draw.rectangle([x, STATUS_BAR_H, x + tab_w - 2, STATUS_BAR_H + TAB_BAR_H], fill=bg)
            label = t["title"] or "New Tab"
            if len(label) > 9:
                label = label[:8] + "\u2026"
            draw.text((x + 8, STATUS_BAR_H + TAB_BAR_H // 2), label, font=FONT_SM,
                       fill=(255, 255, 255), anchor="lm")
            if n > 1:
                draw.text((x + tab_w - 14, STATUS_BAR_H + TAB_BAR_H // 2), "\u2715",
                           font=FONT_SM, fill=(255, 255, 255), anchor="mm")
        draw.rectangle([SCREEN_W - plus_w, STATUS_BAR_H, SCREEN_W, STATUS_BAR_H + TAB_BAR_H],
                       fill=CARD_COLOR)
        draw.text((SCREEN_W - plus_w // 2, STATUS_BAR_H + TAB_BAR_H // 2), "+",
                   font=FONT_MD, fill=(255, 255, 255), anchor="mm")

    def draw(self, draw, canvas):
        self._draw_tab_strip(draw)

        if self.mode == "type":
            draw.text((SCREEN_W // 2, CONTENT_TOP + 18), "Go to URL", font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            draw.rounded_rectangle([16, CONTENT_TOP + 38, SCREEN_W - 16, CONTENT_TOP + 78],
                                    radius=10, fill=CARD_COLOR)
            draw.text((24, CONTENT_TOP + 58), self.draft_url, font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            for b in self.buttons:
                b.draw(draw)
            self.keyboard.draw(draw)
            return

        if self.mode == "bm_edit":
            draw.text((SCREEN_W // 2, CONTENT_TOP + 12),
                       "Edit Bookmark" if self.bm_edit["idx"] is not None else "Add Bookmark",
                       font=FONT_MD, fill=(255, 255, 255), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            y0 = CONTENT_TOP + 8
            draw.text((24, y0 + 47), self.bm_edit["title"] or "Title", font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            draw.text((24, y0 + 89), self.bm_edit["url"] or "URL", font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            self.keyboard.draw(draw)
            return

        if not self.tab["pages"]:
            draw.text((SCREEN_W // 2, CONTENT_TOP + 22), "Bookmarks", font=FONT_LG,
                       fill=(255, 255, 255), anchor="mm")
            if self.status:
                draw.text((SCREEN_W // 2, CONTENT_TOP + 40), self.status, font=FONT_SM,
                           fill=(230, 90, 90), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            return

        draw.text((SCREEN_W // 2, CONTENT_TOP + 12), self.tab["title"] or "", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")

        y = CONTENT_TOP + 32
        for line in self.tab["pages"][self.tab["page_index"]]:
            draw.text((14, y), line, font=FONT_SM, fill=(220, 220, 230), anchor="lm")
            y += 21

        draw.text((SCREEN_W // 2, SCREEN_H - 64),
                   f"Page {self.tab['page_index'] + 1}/{len(self.tab['pages'])}", font=FONT_SM,
                   fill=(150, 150, 160), anchor="mm")
        if self.status:
            draw.text((SCREEN_W // 2, SCREEN_H - 82), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm")

        for b in self.buttons:
            b.draw(draw)
