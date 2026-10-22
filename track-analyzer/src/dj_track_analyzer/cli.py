"""Command line: `uv run dj-track-analyzer <command>`. With no command it runs the MCP server over stdio."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analysis import (analyze_file, check_rules, download_models, log, split_style, style_classes,
                       train)
from .mcp_server import protect_stdout, build_mcp


# Commands that follow the tempo view loaded in Traktor (if any); --native forces the normal library.
VIEW_CMDS = {"hype", "stats", "export"}
# Commands that always use the normal analysis (each track at its own tempo).
NATIVE_CMDS = {"analyze", "scan", "tag", "untag", "traktor", "colors", "regenre"}


def pick_library(args) -> None:
    """Point this command at the loaded tempo view where it makes sense, and say which library it uses."""
    from .analysis import HOME
    from .collection import DB
    from .traktor import TEMPO_STATE

    state = HOME / TEMPO_STATE
    bpm = json.loads(state.read_text()).get("bpm") if state.exists() else None
    if args.cmd in VIEW_CMDS and bpm and not args.native:
        from . import tempo

        tempo.view_db(bpm).close()  # switches collection.DB / the cache to the view
        log(f"Library: {bpm:g} BPM tempo view, loaded in Traktor ({tempo.view_home(bpm)}). "
            "Add --native for each track at its own tempo")
        return
    note = f"Library: normal, each track at its own tempo ({DB})"
    if bpm:
        note += (f"\n  Note: Traktor has the {bpm:g} BPM view loaded, so its Genre/Colour/Comment 2 show "
                 f"{bpm:g} BPM values, not these")
    log(note)


def say_if_nothing(out: dict, dry_run: bool = False) -> None:
    """After a command that writes, say plainly when there was nothing to change."""
    parts = [v for v in out.values() if isinstance(v, dict)] if "changed" not in out else [out]
    flags = [d["changed"] for d in parts if "changed" in d]
    counts = [out[k] for k in ("written", "would_write", "restored", "would_restore", "top_genre_changed") if k in out]
    if (flags and not any(flags)) or (not flags and counts and not any(counts)):
        log("Nothing would change." if dry_run else "Nothing to change: everything is already up to date.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Local track analyzer + MCP server")
    sub = ap.add_subparsers(dest="cmd")
    su = sub.add_parser("setup", help="download the style models")
    su.add_argument("--no-maest", action="store_true", help="skip the larger MAEST genre model")
    sub.add_parser("styles", help="list the 400 Discogs style names and check dj_genres.json")
    a = sub.add_parser("analyze", help="analyze one file and print JSON")
    a.add_argument("file")
    a.add_argument("--segments", type=float, default=None, help="timeline segment length in seconds")
    sc = sub.add_parser("scan", help="analyze a whole collection (resumable), save to database + spreadsheet")
    sc.add_argument("folders", nargs="*", help="folders (or files) to scan")
    sc.add_argument("--traktor", action="store_true", help="scan every track in Traktor's collection (can be combined with folders)")
    sc.add_argument("--nml", default=None, help="path to Traktor's collection.nml (default: found automatically)")
    sc.add_argument("--exclude", action="append", default=[], metavar="FOLDER",
                    help="leave this folder out (repeat for several)")
    sc.add_argument("--include-recordings", action="store_true",
                    help="also scan Traktor's own mix recordings (skipped by default)")
    sc.add_argument("--workers", type=int, default=None, help="parallel analyzers (default: half your CPU cores, max 5)")
    sc.add_argument("--rescan", action="store_true", help="re-analyze files even if already scanned")
    sc.add_argument("--write-tags", metavar="FIELDS", default=None,
                    help="also write results into the files' tags, e.g. genre or genre,bpm,camelot (fields: genre,bpm,key,camelot)")
    sc.add_argument("--csv", default=None, help="where to write the spreadsheet (default data/collection.csv)")
    tg = sub.add_parser("tag", help="write scanned genres (and optionally BPM/key) into your files' tags")
    tg.add_argument("folders", nargs="*", help="limit to these folders (default: everything scanned)")
    tg.add_argument("--fields", default="genre", help="genre (default), or e.g. genre,bpm,camelot  (fields: genre,bpm,key,camelot)")
    tg.add_argument("--min-score", type=float, default=0.0, help="skip tracks whose genre score is below this (e.g. 0.2)")
    tg.add_argument("--use-my-genre", action="store_true", help="write your trained genres instead, where available")
    tg.add_argument("--dry-run", action="store_true", help="show what would change without touching any file")
    tg.add_argument("--multi", action="store_true", help='also add close runner-up genres, e.g. "Acid Trance; Hard Trance"')
    tg.add_argument("--multi-ratio", type=float, default=0.7, help="a runner-up needs at least this share of the top score (default 0.7)")
    tg.add_argument("--max-genres", type=int, default=3, help="most genres per track with --multi (default 3)")
    ut = sub.add_parser("untag", help="restore the genre/BPM/key tags files had before tagging")
    ut.add_argument("folders", nargs="*")
    ut.add_argument("--dry-run", action="store_true")
    tk = sub.add_parser("traktor", help="put tagged genres into Traktor's collection and create genre Smartlists")
    tk.add_argument("--nml", default=None, help="path to collection.nml (default: newest Traktor folder in ~/Documents/Native Instruments)")
    tk.add_argument("--dry-run", action="store_true", help="show what would change without touching anything")
    tk.add_argument("--smartlists-only", action="store_true", help="only (re)create the Smartlists, don't update genres")
    tk.add_argument("--no-smartlists", action="store_true", help="only update genres in the collection")
    tk.add_argument("--undo", action="store_true", help="restore collection.nml from before the last run")
    tk.add_argument("--force", action="store_true",
                    help="with --undo: restore even if Traktor changed the collection since (loses those changes)")
    tk.add_argument("--no-colors", action="store_true", help="don't set predicted colours")
    tk.add_argument("--overwrite-colors", action="store_true", help="also replace colours you set yourself (not recommended)")
    tk.add_argument("--color-min-confidence", type=float, default=0.0, help="only set predicted colours at or above this confidence")
    co = sub.add_parser("colors", help="learn your Traktor colour scale from tracks you've coloured")
    co.add_argument("action", choices=["train", "review", "explain", "apply"],
                    help="train: learn your scale. review: tracks that disagree with their colour "
                         "(--apply recolours the clearest ones in Traktor). "
                         "explain: what each colour means in your collection. "
                         "apply: scan new Traktor tracks and colour the uncoloured ones")
    co.add_argument("--nml", default=None, help="path to collection.nml")
    co.add_argument("--workers", type=int, default=None, help="parallel workers for the deep listening pass")
    co.add_argument("--no-deep", action="store_true", help="skip the MAEST/mood features (faster, less accurate)")
    co.add_argument("--dry-run", action="store_true", help="apply / review --apply: show which colours would be set, change nothing")
    co.add_argument("--min-confidence", type=float, default=None,
                    help="apply: only set predicted colours at or above this confidence (0-1, default 0). "
                         "review --apply: only recolour tracks at or above it (default 0.75)")
    co.add_argument("--apply", action="store_true",
                    help="review: recolour the tracks over the thresholds in Traktor (Traktor closed; backup + traktor --undo)")
    co.add_argument("--yes", action="store_true",
                    help="review --apply: recolour every track over the thresholds without asking about each one")
    co.add_argument("--min-gap", type=float, default=2.5,
                    help="review --apply: only recolour tracks this many colours away from yours or more (default 2.5)")
    co.add_argument("--json", action="store_true", help="explain: print JSON instead of tables")
    hy = sub.add_parser("hype", help="find tracks by how hype they are (1-10), optionally write it to Traktor's Comment 2")
    hy.add_argument("--least", action="store_true", help="least hype (chill) first")
    hy.add_argument("--colour", "--color", dest="colour", default=None, help="only this colour (yours, else predicted)")
    hy.add_argument("--bpm", type=float, default=None, help="only tracks near this BPM")
    hy.add_argument("--bpm-tolerance", type=float, default=4.0, help="BPM window in %% (default 4)")
    hy.add_argument("--key", default=None, help="only tracks that mix with this Camelot key, e.g. 8A")
    hy.add_argument("--gems", action="store_true", help="hype 8+ but rated 4 stars or less, or played at most once")
    hy.add_argument("--limit", type=int, default=25)
    hy.add_argument("--traktor", action="store_true", help="write 'Hype NN' into Comment 2 (Traktor closed)")
    hy.add_argument("--remove", action="store_true", help="with --traktor: take the Hype part out of Comment 2 again")
    hy.add_argument("--dry-run", action="store_true", help="with --traktor: show what would change")
    hy.add_argument("--nml", default=None, help="path to collection.nml")
    hy.add_argument("--native", action="store_true", help="use the normal library even while a tempo view is loaded")
    hy.add_argument("--json", action="store_true", help="print JSON instead of a table")
    te = sub.add_parser("tempo", help="your catalogue as heard at one tempo with key lock (default 145 BPM)")
    te.add_argument("action", choices=["scan", "report", "export", "nml", "load", "native", "refresh", "status"],
                    help="scan: analyse every track stretched to --bpm (cached, resumable). report: what changes. "
                         "export: the view's spreadsheet. nml: a standalone collection.nml of the view. "
                         "load: switch Traktor to the view (Traktor closed). native: switch back. "
                         "refresh: redo genres/colours/hype from the cache. status")
    te.add_argument("--bpm", type=float, default=145.0, help="the tempo you play at (default 145)")
    te.add_argument("--workers", type=int, default=None, help="scan: parallel analyzers (default: half your CPU cores, max 5)")
    te.add_argument("--rescan", action="store_true", help="scan: analyse again even if cached")
    te.add_argument("--nml", default=None, help="path to Traktor's collection.nml")
    te.add_argument("--out", default=None, help="export / nml: where to write (default data/at-<bpm>/)")
    te.add_argument("--dry-run", action="store_true", help="load / native: show what would change")
    te.add_argument("--force", action="store_true",
                    help="load: even while Traktor is set to write tags to your files")
    te.add_argument("--lexicon", action="store_true",
                    help="load / native: switch Lexicon too (Lexicon open, Settings → Integrations → Local API on)")
    te.add_argument("--limit", type=int, default=15, help="report: tracks per list")
    te.add_argument("--json", action="store_true", help="report: print JSON")
    sub.add_parser("regenre", help="recompute the genres of scanned tracks from the cache (after editing dj_genres.json)")
    ex = sub.add_parser("export", help="write the scanned collection to a CSV spreadsheet")
    ex.add_argument("out", nargs="?", default=None)
    ex.add_argument("--native", action="store_true", help="use the normal library even while a tempo view is loaded")
    st = sub.add_parser("stats", help="summary of the scanned collection")
    st.add_argument("--native", action="store_true", help="use the normal library even while a tempo view is loaded")
    t = sub.add_parser("train", help="train your own genres from a folder")
    t.add_argument("folder")
    s = sub.add_parser("serve", help="run the MCP server")
    s.add_argument("--http", action="store_true", help="streamable HTTP instead of stdio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if args.cmd in VIEW_CMDS | NATIVE_CMDS:
        pick_library(args)

    if args.cmd == "setup":
        download_models(maest=not args.no_maest)
        check_rules()
    elif args.cmd == "styles":
        names = [split_style(c)[0] for c in style_classes()]
        print("\n".join(sorted(set(names))))
        check_rules()
    elif args.cmd == "analyze":
        print(json.dumps(analyze_file(args.file, args.segments, progress=True), indent=2, ensure_ascii=False))
    elif args.cmd == "train":
        print(json.dumps(train(args.folder), indent=2, ensure_ascii=False))
    elif args.cmd == "scan":
        from . import collection

        collection.main_scan(args)
    elif args.cmd == "tag":
        from . import collection

        fields = [f.strip().lower() for f in args.fields.split(",") if f.strip()]
        bad = set(fields) - {"genre", "bpm", "key", "camelot"}
        if bad or ("key" in fields and "camelot" in fields):
            raise SystemExit("--fields takes genre,bpm,key,camelot (key OR camelot, not both)")
        out = collection.tag_from_db(args.folders or None, fields, args.min_score, args.use_my_genre, args.dry_run,
                                     args.multi, args.multi_ratio, args.max_genres)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        say_if_nothing(out, args.dry_run)
    elif args.cmd == "untag":
        from . import collection

        out = collection.untag(args.folders or None, args.dry_run)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        say_if_nothing(out, args.dry_run)
    elif args.cmd == "traktor":
        from . import traktor

        if args.undo:
            out = traktor.undo(args.nml, force=args.force)
        else:
            out = traktor.sync(args.nml, args.dry_run, update_genres=not args.smartlists_only,
                               make_smartlists=not args.no_smartlists, colors=not args.no_colors,
                               overwrite_colors=args.overwrite_colors,
                               color_min_confidence=args.color_min_confidence)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if not args.undo:
            say_if_nothing(out, args.dry_run)
    elif args.cmd == "colors":
        from . import colors

        if args.action == "explain":
            out = colors.explain(args.nml, workers=args.workers)
            print(json.dumps(out, indent=2, ensure_ascii=False) if args.json else colors.explain_text(out))
            return
        if args.action == "train":
            out = colors.train(args.nml, deep=not args.no_deep, workers=args.workers)
        elif args.action == "apply":
            out = colors.apply(args.nml, dry_run=args.dry_run, min_confidence=args.min_confidence or 0.0,
                               workers=args.workers)
        else:
            out = colors.review(apply=args.apply, dry_run=args.dry_run, min_gap=args.min_gap,
                                min_confidence=0.75 if args.min_confidence is None else args.min_confidence,
                                nml=args.nml, ask=sys.stdin.isatty() and not args.yes)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        if args.action == "apply" or args.apply:
            say_if_nothing(out, args.dry_run)
    elif args.cmd == "hype":
        from . import hype

        if args.traktor:
            out = hype.to_traktor(args.nml, dry_run=args.dry_run, remove=args.remove)
            print(json.dumps(out, indent=2, ensure_ascii=False))
            say_if_nothing(out, args.dry_run)
            return
        out = hype.find(args.nml, least=args.least, colour=args.colour, bpm=args.bpm,
                        bpm_tolerance_pct=args.bpm_tolerance, key=args.key, gems=args.gems, limit=args.limit)
        print(json.dumps(out, indent=2, ensure_ascii=False) if args.json else hype.find_text(out))
    elif args.cmd == "tempo":
        from . import tempo

        tempo.main(args)
    elif args.cmd == "regenre":
        from . import collection

        out = collection.regenre()
        print(json.dumps(out, indent=2, ensure_ascii=False))
        say_if_nothing(out)
    elif args.cmd == "export":
        from . import collection

        collection.export_csv(Path(args.out) if args.out else collection.DEFAULT_CSV)
    elif args.cmd == "stats":
        from . import collection

        print(json.dumps(collection.summary(), indent=2, ensure_ascii=False))
    elif args.cmd == "serve" and args.http:
        log(f"Track Analyzer MCP on http://{args.host}:{args.port}/mcp")
        build_mcp().run(transport="streamable-http", host=args.host, port=args.port)
    else:  # default: stdio for LM Studio / Claude Desktop
        protect_stdout()
        build_mcp().run(transport="stdio")
