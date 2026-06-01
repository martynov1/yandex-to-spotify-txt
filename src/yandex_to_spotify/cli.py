from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from yandex_to_spotify.models import Track
from yandex_to_spotify.spotify_client import SpotifyClient
from yandex_to_spotify.transfer import TransferReport, transfer_playlist
from yandex_to_spotify.yandex_client import YandexClient

console = Console()


def _load_env() -> None:
    load_dotenv()
    load_dotenv(Path.cwd() / ".env", override=False)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        console.print(f"[red]Не задана переменная окружения {name}. См. .env.example[/red]")
        sys.exit(1)
    return value


def _build_spotify() -> SpotifyClient:
    return SpotifyClient(
        client_id=_require_env("SPOTIFY_CLIENT_ID"),
        client_secret=_require_env("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=_require_env("SPOTIFY_REDIRECT_URI"),
    )


def _slug(text: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in text)
    return safe.strip("_") or "playlist"


def _write_unmatched(report: TransferReport, path: Path) -> None:
    path.write_text(
        "\n".join(str(t) for t in report.unmatched),
        encoding="utf-8",
    )


def _write_review(report: TransferReport, path: Path) -> None:
    lines = []
    for m in report.review:
        lines.append(
            f"[{m.score:.2f}] {m.source}  →  {m.spotify_artists} — {m.spotify_title}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _print_summary(report: TransferReport, *, dry_run: bool) -> None:
    prefix = "Dry-run: " if dry_run else ""
    console.print()
    console.print(
        f"[bold green]{prefix}Готово.[/bold green] "
        f"Сопоставлено: {len(report.matched)}/{report.total} "
        f"({report.match_rate:.1f}%)"
    )
    if report.playlist_id:
        console.print(f"Spotify playlist id: [cyan]{report.playlist_id}[/cyan]")
    if report.review:
        console.print(
            f"[yellow]Низкая уверенность: {len(report.review)} треков — стоит проверить.[/yellow]"
        )


@click.group()
def main() -> None:
    """Импорт плейлистов из Яндекс Музыки в Spotify."""
    _load_env()


@main.command("list")
def list_playlists() -> None:
    """Показать список плейлистов пользователя в Яндекс Музыке."""
    yandex = YandexClient(_require_env("YANDEX_MUSIC_TOKEN"))
    items = yandex.list_playlists()

    table = Table(title="Плейлисты Яндекс Музыки", show_lines=False)
    table.add_column("kind", style="cyan", no_wrap=True)
    table.add_column("Название", style="white")
    table.add_column("Треков", justify="right", style="dim")
    for item in items:
        table.add_row(item.kind, item.title, str(item.track_count) if item.track_count else "")
    console.print(table)
    console.print("\nДля импорта используйте: [bold]yandex-to-spotify import <kind>[/bold]")


_common_options = [
    click.option("--name", "new_name", default=None, help="Имя плейлиста в Spotify (по умолчанию — исходное)."),
    click.option("--public/--private", default=False, help="Сделать плейлист публичным."),
    click.option(
        "--threshold",
        type=float,
        default=0.6,
        show_default=True,
        help="Минимальный score совпадения трека (0..1).",
    ),
    click.option(
        "--dry-run",
        is_flag=True,
        help="Только сопоставить треки, не создавать плейлист в Spotify.",
    ),
    click.option(
        "--unmatched-out",
        type=click.Path(dir_okay=False, writable=True),
        default=None,
        help="Файл для записи треков, которые не удалось найти.",
    ),
    click.option(
        "--review-out",
        type=click.Path(dir_okay=False, writable=True),
        default=None,
        help="Файл для записи сопоставлений с низкой уверенностью.",
    ),
]


def _apply_common_options(cmd):
    for option in reversed(_common_options):
        cmd = option(cmd)
    return cmd


def _run_one(
    yandex: YandexClient,
    spotify: SpotifyClient,
    kind: str,
    *,
    new_name: str | None,
    public: bool,
    threshold: float,
    dry_run: bool,
    unmatched_out: str | None,
    review_out: str | None,
) -> TransferReport:
    console.print(f"[bold]Загружаю плейлист из Яндекс Музыки:[/bold] {kind}")
    playlist = yandex.fetch_playlist(kind)
    console.print(f"Получено треков: [cyan]{len(playlist.tracks)}[/cyan]")

    if not playlist.tracks:
        console.print("[yellow]Плейлист пуст — нечего импортировать.[/yellow]")
        return TransferReport(playlist_id=None)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Ищу треки в Spotify", total=len(playlist.tracks))

        def _on_progress(done: int, total: int, _track: Track) -> None:
            progress.update(task, completed=done, total=total)

        def _on_log(msg: str) -> None:
            console.print(msg)

        report = transfer_playlist(
            spotify,
            playlist,
            new_name=new_name,
            public=public,
            threshold=threshold,
            dry_run=dry_run,
            on_progress=_on_progress,
            on_log=_on_log,
        )

    _print_summary(report, dry_run=dry_run)

    tag = report.playlist_id or _slug(new_name or playlist.title)
    if report.unmatched:
        out_path = Path(unmatched_out) if unmatched_out else Path(f"unmatched_{tag}.txt")
        _write_unmatched(report, out_path)
        console.print(
            f"[yellow]Не найдено в Spotify: {len(report.unmatched)} треков[/yellow] → [cyan]{out_path}[/cyan]"
        )
    if report.review:
        path = Path(review_out) if review_out else Path(f"review_{tag}.txt")
        _write_review(report, path)
        console.print(f"Низкая уверенность записана в [cyan]{path}[/cyan]")
    return report


@main.command("import")
@click.argument("kind")
@_apply_common_options
def import_playlist(
    kind: str,
    new_name: str | None,
    public: bool,
    threshold: float,
    dry_run: bool,
    unmatched_out: str | None,
    review_out: str | None,
) -> None:
    """Импортировать плейлист (по kind, см. `list`) в Spotify."""
    yandex = YandexClient(_require_env("YANDEX_MUSIC_TOKEN"))
    spotify = _build_spotify()
    _run_one(
        yandex,
        spotify,
        kind,
        new_name=new_name,
        public=public,
        threshold=threshold,
        dry_run=dry_run,
        unmatched_out=unmatched_out,
        review_out=review_out,
    )


@main.command("import-all")
@click.option("--public/--private", default=False, help="Сделать плейлисты публичными.")
@click.option(
    "--threshold",
    type=float,
    default=0.6,
    show_default=True,
    help="Минимальный score совпадения трека (0..1).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Только сопоставить треки, не создавать плейлисты.",
)
@click.option(
    "--skip-liked",
    is_flag=True,
    help="Не импортировать «Мне нравится».",
)
@click.option(
    "--prefix",
    default="",
    help="Префикс к имени плейлиста в Spotify, напр. '[YM] '.",
)
def import_all(
    public: bool,
    threshold: float,
    dry_run: bool,
    skip_liked: bool,
    prefix: str,
) -> None:
    """Импортировать все плейлисты пользователя."""
    yandex = YandexClient(_require_env("YANDEX_MUSIC_TOKEN"))
    spotify = _build_spotify()

    items = yandex.list_playlists()
    if skip_liked:
        items = [it for it in items if it.kind != "liked"]

    if not items:
        console.print("[yellow]Нет плейлистов для импорта.[/yellow]")
        return

    console.print(f"К импорту: [cyan]{len(items)}[/cyan] плейлистов")
    aggregate: list[tuple[str, TransferReport]] = []
    for item in items:
        console.rule(f"[bold]{item.title}[/bold] ({item.kind})")
        target_name = f"{prefix}{item.title}" if prefix else item.title
        try:
            report = _run_one(
                yandex,
                spotify,
                item.kind,
                new_name=target_name,
                public=public,
                threshold=threshold,
                dry_run=dry_run,
                unmatched_out=None,
                review_out=None,
            )
        except Exception as exc:  # noqa: BLE001 — одиночный сбой не должен валить всю серию
            console.print(f"[red]Ошибка при импорте «{item.title}»:[/red] {exc}")
            continue
        aggregate.append((item.title, report))

    console.rule("[bold]Итог[/bold]")
    table = Table(show_lines=False)
    table.add_column("Плейлист", style="white")
    table.add_column("Совпало", justify="right")
    table.add_column("Не найдено", justify="right", style="yellow")
    table.add_column("На проверку", justify="right", style="yellow")
    for title, report in aggregate:
        table.add_row(
            title,
            f"{len(report.matched)}/{report.total}",
            str(len(report.unmatched)),
            str(len(report.review)),
        )
    console.print(table)
