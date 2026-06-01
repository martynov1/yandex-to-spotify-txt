"""Customtkinter desktop UI: подключение к Yandex Music и экспорт плейлистов в .txt.

Worker-потоки делают всю сетевую работу; основной Tk-цикл опрашивает очередь событий.
"""

from __future__ import annotations

import os
import platform
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from dotenv import load_dotenv

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

from yandex_to_spotify.models import PlaylistSummary
from yandex_to_spotify.yandex_client import YandexClient

# Палитра в духе Spotify (всё ещё уместна — приложение про музыку).
BG = "#000000"
SURFACE = "#121212"
SURFACE_ALT = "#1A1A1A"
ELEVATED = "#242424"
ELEVATED_ALT = "#2E2E2E"
GREEN = "#1ED760"
GREEN_HOVER = "#3BE477"
GREEN_PRESSED = "#17B14F"
ON_GREEN = "#000000"
TEXT = "#FFFFFF"
TEXT_DIM = "#C7C7C7"
TEXT_MUTED = "#8A8A8A"
DANGER = "#FF6E7A"
WARNING = "#F2C94C"
BORDER = "#2F2F2F"


@dataclass
class _PlaylistRow:
    summary: PlaylistSummary
    var: ctk.BooleanVar
    frame: ctk.CTkFrame


class YandexToSpotifyApp(ctk.CTk):
    POLL_MS = 80

    def __init__(self) -> None:
        super().__init__()
        load_dotenv()

        ctk.set_appearance_mode("dark")

        self.title("Yandex → TXT")
        self.geometry("980x760")
        self.minsize(820, 620)
        self.configure(fg_color=BG)
        self._apply_icon()

        self._font_h1 = ctk.CTkFont(family="SF Pro Display", size=26, weight="bold")
        self._font_h2 = ctk.CTkFont(family="SF Pro Display", size=15, weight="bold")
        self._font_body = ctk.CTkFont(family="SF Pro Text", size=13)
        self._font_small = ctk.CTkFont(family="SF Pro Text", size=11)
        self._font_button = ctk.CTkFont(family="SF Pro Text", size=15, weight="bold")
        self._font_button_sm = ctk.CTkFont(family="SF Pro Text", size=12, weight="bold")
        self._font_mono = ctk.CTkFont(family="SF Mono", size=12)

        self._events: queue.Queue[tuple] = queue.Queue()
        self._yandex: YandexClient | None = None
        self._rows: list[_PlaylistRow] = []
        self._worker: threading.Thread | None = None

        self._build_layout()
        self.after(self.POLL_MS, self._drain_events)

    # ──────────────────────────────────────────────────────────────────────
    # Icon
    # ──────────────────────────────────────────────────────────────────────

    def _apply_icon(self) -> None:
        icon_path = ASSETS_DIR / "icon.png"
        if not icon_path.exists():
            return
        try:
            photo = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, photo)
            self._icon_photo = photo
        except tk.TclError:
            pass

        if platform.system() == "Darwin":
            self._set_macos_dock_icon(icon_path)

    def _set_macos_dock_icon(self, icon_path: Path) -> None:
        try:
            from AppKit import NSApplication, NSImage  # type: ignore
        except ImportError:
            return
        try:
            image = NSImage.alloc().initByReferencingFile_(str(icon_path))
            NSApplication.sharedApplication().setApplicationIconImage_(image)
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # Layout
    # ──────────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_credentials_card()
        self._build_playlists()
        self._build_action_bar()
        self._build_log()
        self._build_status_bar()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 12))
        header.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkFrame(header, fg_color=GREEN, corner_radius=24, width=48, height=48)
        badge.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 16))
        badge.grid_propagate(False)
        ctk.CTkLabel(
            badge, text="♪", font=ctk.CTkFont(size=26, weight="bold"), text_color=ON_GREEN
        ).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            header, text="Yandex → TXT", font=self._font_h1, text_color=TEXT, anchor="w"
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(
            header,
            text="Экспорт плейлистов Яндекс Музыки в текстовые файлы",
            font=self._font_small,
            text_color=TEXT_DIM,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

    def _build_credentials_card(self) -> None:
        card = self._card(self)
        card.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)

        self._section_label(card, "Подключение").grid(
            row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 14)
        )

        self._field_label(card, "Yandex token").grid(
            row=1, column=0, sticky="w", padx=(20, 12), pady=4
        )
        yandex_wrap, self._yandex_token = self._entry_with_paste(card, show="•")
        yandex_wrap.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)
        self._yandex_token.insert(0, os.environ.get("YANDEX_MUSIC_TOKEN", ""))

        self._connect_btn = self._primary_button(card, "Подключиться", self._on_connect)
        self._connect_btn.grid(row=1, column=2, sticky="e", padx=(0, 20), pady=4)

    def _build_playlists(self) -> None:
        card = self._card(self)
        card.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        self._section_label(header, "Плейлисты").grid(row=0, column=0, sticky="w")
        self._playlists_count = ctk.CTkLabel(
            header, text="", font=self._font_small, text_color=TEXT_MUTED
        )
        self._playlists_count.grid(row=0, column=1, sticky="e", padx=(0, 12))
        self._select_all_btn = self._ghost_button(header, "Все", lambda: self._set_all(True))
        self._select_all_btn.grid(row=0, column=2, padx=(0, 6))
        self._clear_btn = self._ghost_button(header, "Снять", lambda: self._set_all(False))
        self._clear_btn.grid(row=0, column=3)

        self._playlists_view = ctk.CTkScrollableFrame(
            card,
            fg_color=BG,
            scrollbar_button_color=ELEVATED,
            scrollbar_button_hover_color=TEXT_MUTED,
            corner_radius=8,
        )
        self._playlists_view.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self._playlists_view.grid_columnconfigure(0, weight=1)

        self._playlists_placeholder = ctk.CTkLabel(
            self._playlists_view,
            text="Подключитесь, чтобы загрузить список плейлистов.",
            font=self._font_body,
            text_color=TEXT_MUTED,
        )
        self._playlists_placeholder.grid(row=0, column=0, pady=40)

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 12))
        bar.grid_columnconfigure(1, weight=1)

        self._export_btn = self._primary_button(
            bar, "Экспортировать в TXT", self._on_export, width=240, height=44
        )
        self._export_btn.configure(state="disabled")
        self._export_btn.grid(row=0, column=0, sticky="w")

        progress_wrap = ctk.CTkFrame(bar, fg_color="transparent")
        progress_wrap.grid(row=0, column=1, sticky="ew", padx=(16, 16))
        progress_wrap.grid_columnconfigure(0, weight=1)

        self._progress_label = ctk.CTkLabel(
            progress_wrap, text="", font=self._font_small, text_color=TEXT_DIM, anchor="w"
        )
        self._progress_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._progress = ctk.CTkProgressBar(
            progress_wrap, progress_color=GREEN, fg_color=ELEVATED, height=6, corner_radius=3
        )
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew")

    def _build_log(self) -> None:
        card = self._card(self)
        card.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)

        self._section_label(card, "Журнал").grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))
        self._log = ctk.CTkTextbox(
            card,
            height=160,
            wrap="word",
            font=self._font_mono,
            fg_color=BG,
            text_color=TEXT_DIM,
            border_width=0,
            corner_radius=8,
        )
        self._log.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._log.configure(state="disabled")

    def _build_status_bar(self) -> None:
        self._status_dot = ctk.CTkLabel(self, text="●", font=self._font_body, text_color=TEXT_MUTED)
        self._status_dot.grid(row=5, column=0, sticky="w", padx=(28, 0), pady=(0, 18))
        self._status = ctk.CTkLabel(
            self, text="Не подключено", font=self._font_small, text_color=TEXT_DIM, anchor="w"
        )
        self._status.grid(row=5, column=0, sticky="w", padx=(48, 0), pady=(0, 18))

    # ──────────────────────────────────────────────────────────────────────
    # Reusable styled widgets
    # ──────────────────────────────────────────────────────────────────────

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=12)

    def _section_label(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=self._font_h2, text_color=TEXT, anchor="w")

    def _field_label(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text, font=self._font_small, text_color=TEXT_DIM, anchor="w", width=110
        )

    def _entry(self, parent, show: str | None = None, placeholder: str = "") -> ctk.CTkEntry:
        kwargs = dict(
            fg_color=ELEVATED,
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            placeholder_text_color=TEXT_MUTED,
            corner_radius=8,
            height=32,
            font=self._font_body,
        )
        if show is not None:
            kwargs["show"] = show
        if placeholder:
            kwargs["placeholder_text"] = placeholder
        entry = ctk.CTkEntry(parent, **kwargs)
        inner = getattr(entry, "_entry", None)
        if inner is not None:
            def _paste(e):
                try:
                    text = entry.clipboard_get()
                except Exception:
                    return "break"
                if inner.selection_present():
                    inner.delete("sel.first", "sel.last")
                inner.insert("insert", text)
                return "break"

            def _copy(e):
                if inner.selection_present():
                    entry.clipboard_clear()
                    entry.clipboard_append(inner.selection_get())
                return "break"

            def _cut(e):
                if inner.selection_present():
                    entry.clipboard_clear()
                    entry.clipboard_append(inner.selection_get())
                    inner.delete("sel.first", "sel.last")
                return "break"

            def _select_all(e):
                inner.select_range(0, "end")
                inner.icursor("end")
                return "break"

            for seq, handler in (
                ("<<Paste>>", _paste),
                ("<<Copy>>", _copy),
                ("<<Cut>>", _cut),
                ("<<SelectAll>>", _select_all),
                ("<Command-v>", _paste),
                ("<Command-V>", _paste),
                ("<Control-v>", _paste),
                ("<Command-c>", _copy),
                ("<Command-x>", _cut),
                ("<Command-a>", _select_all),
            ):
                inner.bind(seq, handler)
        return entry

    def _entry_with_paste(
        self, parent, show: str | None = None, placeholder: str = ""
    ) -> tuple[ctk.CTkFrame, ctk.CTkEntry]:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid_columnconfigure(0, weight=1)
        entry = self._entry(wrap, show=show, placeholder=placeholder)
        entry.grid(row=0, column=0, sticky="ew")

        def _paste_from_clipboard() -> None:
            try:
                text = wrap.clipboard_get()
            except Exception:
                return
            entry.delete(0, "end")
            entry.insert(0, text.strip())

        ctk.CTkButton(
            wrap,
            text="Вставить",
            width=78,
            height=32,
            command=_paste_from_clipboard,
            fg_color=ELEVATED_ALT,
            hover_color=BORDER,
            text_color=TEXT,
            font=self._font_small,
            corner_radius=8,
        ).grid(row=0, column=1, padx=(6, 0))
        return wrap, entry

    def _primary_button(
        self, parent, text: str, command, *, width: int = 0, height: int = 44
    ) -> ctk.CTkButton:
        kwargs = dict(
            text=text.upper(),
            command=command,
            fg_color=GREEN,
            hover_color=GREEN_HOVER,
            text_color=ON_GREEN,
            text_color_disabled="#1F1F1F",
            font=self._font_button,
            corner_radius=999,
            height=height,
        )
        if width:
            kwargs["width"] = width
        return ctk.CTkButton(parent, **kwargs)

    def _ghost_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color="transparent",
            hover_color=ELEVATED,
            text_color=TEXT,
            font=self._font_button_sm,
            height=30,
            width=72,
            corner_radius=999,
            border_color=BORDER,
            border_width=1,
        )

    # ──────────────────────────────────────────────────────────────────────
    # UI helpers
    # ──────────────────────────────────────────────────────────────────────

    def _log_line(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_status(self, text: str, dot_color: str = TEXT_MUTED) -> None:
        self._status.configure(text=text)
        self._status_dot.configure(text_color=dot_color)

    def _set_all(self, value: bool) -> None:
        for row in self._rows:
            row.var.set(value)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._connect_btn.configure(state=state)
        connected = self._yandex is not None
        self._export_btn.configure(state="disabled" if busy or not connected else "normal")

    def _populate_playlists(self, items: list[PlaylistSummary]) -> None:
        for child in self._playlists_view.winfo_children():
            child.destroy()
        self._rows = []

        if not items:
            ctk.CTkLabel(
                self._playlists_view,
                text="Плейлисты не найдены.",
                font=self._font_body,
                text_color=TEXT_MUTED,
            ).grid(row=0, column=0, pady=40)
            self._playlists_count.configure(text="")
            return

        for i, item in enumerate(items):
            row = self._build_playlist_row(self._playlists_view, item, index=i)
            row.frame.grid(row=i, column=0, sticky="ew", padx=4, pady=3)
            self._rows.append(row)
        self._playlists_count.configure(text=f"{len(items)} в списке")

    def _build_playlist_row(self, parent, item: PlaylistSummary, *, index: int) -> _PlaylistRow:
        bg = ELEVATED if index % 2 == 0 else SURFACE_ALT
        frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8, height=56)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_propagate(False)

        var = ctk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(
            frame,
            text="",
            variable=var,
            width=24,
            checkbox_width=20,
            checkbox_height=20,
            corner_radius=4,
            fg_color=GREEN,
            hover_color=GREEN_HOVER,
            border_color=TEXT_MUTED,
            border_width=2,
        )
        checkbox.grid(row=0, column=0, rowspan=2, sticky="w", padx=(16, 12), pady=8)

        title = ctk.CTkLabel(frame, text=item.title, font=self._font_body, text_color=TEXT, anchor="w")
        title.grid(row=0, column=1, sticky="ew", pady=(8, 0))

        subtitle_text = item.kind
        if item.track_count:
            subtitle_text = f"{item.track_count} треков  ·  {item.kind}"
        subtitle = ctk.CTkLabel(
            frame, text=subtitle_text, font=self._font_small, text_color=TEXT_MUTED, anchor="w"
        )
        subtitle.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        def _toggle(_event=None) -> None:
            var.set(not var.get())

        for widget in (frame, title, subtitle):
            widget.bind("<Button-1>", _toggle)

        return _PlaylistRow(summary=item, var=var, frame=frame)

    # ──────────────────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────────────────

    def _on_connect(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        token = self._yandex_token.get().strip()
        if not token:
            self._log_line("Введите Yandex token.")
            return

        self._set_busy(True)
        self._set_status("Подключаюсь…", dot_color=WARNING)
        self._log_line("Подключаюсь к Yandex Music…")
        self._worker = threading.Thread(
            target=self._connect_worker, args=(token,), daemon=True
        )
        self._worker.start()

    def _on_export(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self._yandex:
            return
        selected = [r.summary for r in self._rows if r.var.get()]
        if not selected:
            self._log_line("Выберите хотя бы один плейлист.")
            return

        target_dir = filedialog.askdirectory(
            title="Куда сохранить TXT-файлы?",
            initialdir=str(Path.home() / "Downloads"),
        )
        if not target_dir:
            self._log_line("Экспорт отменён.")
            return

        self._set_busy(True)
        self._set_status("Экспорт…", dot_color=WARNING)
        self._progress.set(0)
        self._progress_label.configure(text="")
        self._log_line(f"Экспортирую {len(selected)} плейлист(ов) в {target_dir}.")
        self._worker = threading.Thread(
            target=self._export_worker, args=(selected, Path(target_dir)), daemon=True
        )
        self._worker.start()

    # ──────────────────────────────────────────────────────────────────────
    # Workers
    # ──────────────────────────────────────────────────────────────────────

    def _emit(self, *event: object) -> None:
        self._events.put(event)

    def _connect_worker(self, token: str) -> None:
        try:
            yandex = YandexClient(token)
            playlists = yandex.list_playlists()
        except Exception as exc:  # noqa: BLE001
            self._emit("error", f"Не удалось подключиться: {exc}")
            return
        self._emit("connected", yandex, playlists)

    def _export_worker(self, selected: list[PlaylistSummary], target_dir: Path) -> None:
        assert self._yandex
        target_dir.mkdir(parents=True, exist_ok=True)
        written: list[tuple[str, Path, int]] = []
        total_playlists = len(selected)

        for idx, summary in enumerate(selected, start=1):
            self._emit("log", f"[{idx}/{total_playlists}] {summary.title}")
            self._emit("progress", summary.title, idx - 1, total_playlists)
            try:
                playlist = self._yandex.fetch_playlist(summary.kind)
            except Exception as exc:  # noqa: BLE001
                self._emit("log", f"  ✕ не удалось загрузить: {exc}")
                continue

            if not playlist.tracks:
                self._emit("log", "  пусто, пропускаю.")
                continue

            filename = _slug(playlist.title) + ".txt"
            out_path = target_dir / filename
            lines = [f"{t.artists_str} - {t.title}" for t in playlist.tracks]
            try:
                out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError as exc:
                self._emit("log", f"  ✕ не удалось записать: {exc}")
                continue

            written.append((summary.title, out_path, len(lines)))
            self._emit("log", f"  ✓ {len(lines)} треков → {out_path.name}")
            self._emit("progress", summary.title, idx, total_playlists)

        self._emit("done", written, target_dir)

    # ──────────────────────────────────────────────────────────────────────
    # Event pump
    # ──────────────────────────────────────────────────────────────────────

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.after(self.POLL_MS, self._drain_events)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "log":
            self._log_line(event[1])
        elif kind == "error":
            self._log_line(f"✕ {event[1]}")
            self._set_status("Ошибка", dot_color=DANGER)
            self._set_busy(False)
        elif kind == "connected":
            self._yandex, playlists = event[1], event[2]
            self._populate_playlists(playlists)
            self._set_status(f"Подключено · Yandex · {len(playlists)} плейлистов", dot_color=GREEN)
            self._log_line(f"Готово. Найдено плейлистов: {len(playlists)}.")
            self._set_busy(False)
        elif kind == "progress":
            title, done, total = event[1], event[2], event[3]
            self._progress.set(done / total if total else 0)
            self._progress_label.configure(text=f"{title}  ·  {done}/{total}")
        elif kind == "done":
            written, target_dir = event[1], event[2]
            total_tracks = sum(n for _, _, n in written)
            self._log_line(
                f"Готово. {len(written)} файл(ов), всего {total_tracks} треков → {target_dir}"
            )
            self._set_status("Готово", dot_color=GREEN)
            self._progress.set(1 if written else 0)
            self._progress_label.configure(text="")
            self._set_busy(False)


def _slug(text: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in text).strip()
    safe = "_".join(safe.split())
    return safe or "playlist"


def main() -> None:
    app = YandexToSpotifyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
