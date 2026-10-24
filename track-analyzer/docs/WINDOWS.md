# Windows: what a port would take

Track Analyzer runs on macOS and Linux (x86_64). It does not run on Windows yet. These notes list what stands
in the way, found by reading the code (October 2026); nothing here has been tried on a Windows machine. Items
marked **verify** are guesses about Traktor or Lexicon on Windows that need a real Windows install to confirm.

## The blocker: Essentia

`essentia-tensorflow` has pip wheels for macOS (arm64, x86_64) and Linux x86_64 only, so `uv sync` fails on
Windows and nothing runs. Essentia doesn't support native Windows builds with TensorFlow.
There are two ways around it:

1. **WSL2 (recommended).** Ubuntu under WSL2 runs the Linux build unchanged; everything that works on Linux
   works there. The work is in reaching Traktor on the Windows side (next section). The web page on
   127.0.0.1:8766 opens in the Windows browser, since WSL2 forwards localhost.
2. **Native Windows.** Needs Essentia built from source with TensorFlow for Windows, a large and fragile job.
   Not worth it while WSL2 works.

Pick one before starting, because the path handling below depends on it.

## Traktor

Traktor runs on Windows (not on Linux), so the Traktor half of the tool is what a port really adds.

- **Collection location.** `traktor.find_collection()` globs `~/Documents/Native Instruments/Traktor*/collection.nml`.
  Native Windows: the same relative to the user folder, so `expanduser` finds it (**verify**: OneDrive can move
  Documents to `~/OneDrive/Documents`). WSL2: the Linux home is not the Windows one; look in
  `/mnt/c/Users/<windows user>/Documents/Native Instruments/` (the Windows user name from
  `cmd.exe /c echo %USERNAME%` or `wslvar USERNAME`). History files (`tracklist.HISTORY_GLOB`) and recordings
  (`traktor.recording_dirs()`) use the same base.
- **Track paths.** `traktor.location_paths()` turns an NML `LOCATION` (`VOLUME`, `DIR="/:Users/:me/:Music/:"`, `FILE`)
  into `/Users/…` or `/Volumes/<VOLUME>/…`. On Windows `VOLUME` is a drive letter (`VOLUME="C:"`, **verify** the
  exact form and `VOLUMEID`), so the path is `C:/Users/me/Music/x.mp3` natively or `/mnt/c/Users/me/Music/x.mp3`
  under WSL2. Every lookup between Traktor's entries and `collection.db` paths goes through this, so get it
  right first; a wrong mapping means no track matches. Network drives (`\\server\share`) need a rule too.
- **Settings paths.** `traktor.mac_path()` converts the `.tsi`'s colon paths (`Macintosh HD:Users:Shared:…`). Windows
  Traktor's form is unknown (**verify**: probably `C:\Users\…` or a colon form with a drive letter). Used for
  the sample folder (`web.sample_root()`) and the folders `scan --traktor` skips.
- **Is Traktor running?** `traktor.traktor_running()` uses `pgrep`. On Windows that command doesn't exist, the
  call fails, and the function returns False: every writer would then edit `collection.nml` while Traktor is
  open, and Traktor overwrites it on quit. Use `tasklist /FI "IMAGENAME eq Traktor.exe"` (from WSL2:
  `tasklist.exe`; **verify** the process name), and make a failed check refuse to write rather than assume
  Traktor is closed.
- **NML text.** The NML is read and written with `Path.read_text()` / `write_text()` without an encoding in many
  places (18 at the time of writing). Python on Windows defaults to the ANSI code page, so accented
  names would be garbled or the write would fail. Pass `encoding="utf-8"` everywhere, or run Python in UTF-8
  mode (`PYTHONUTF8=1`, set in the launcher). Under WSL2 this doesn't apply.
- **Line endings.** The NML edits are surgical text edits; check that reading and writing keeps Traktor's line endings
  (`newline=""`), or the backup/undo SHA-1 check (`.written-sha1`) will report every file as changed.
- **MODIFIED stamps.** `traktor.file_stamp()` uses the file's mtime; NTFS mtimes are fine. Through WSL2's
  `/mnt/c` they come through too (**verify** that the seconds match what Traktor writes).

## Paths inside the code

Paths are stored as `str(Path)` strings and compared as strings. Natively that means backslashes, and
several places assume `/`:

- `collection.py` folder matching: `path.startswith(r.rstrip("/") + "/")` (in `_under`, the scan's exclude list,
  the "gone" check), `jobs.py` skip check (`d + "/"`).
- `collection._missing_for_good()` knows macOS `/Volumes/<disk>` and Linux `/media`, `/run/media`, `/mnt` for
  unplugged drives. Natively, add drive letters (a missing `E:\` drive means unplugged, not deleted).
- `collection.nfc()` composes accented names only where a file has that name (NTFS doesn't normalise),
  so it already behaves on Windows.
- `clips.py` puts previews in `/tmp` when it exists, else the system temp folder: fine.
- Paths over 260 characters need long-path support turned on in Windows.

Under WSL2 all of this is Linux and already works.

## The web page's Setup tab

- **Stopping a job.** `jobs.py` starts each job with `start_new_session=True` and stops it with `os.killpg(…, SIGINT)`,
  then SIGTERM. Windows has neither. Natively: start with `creationflags=CREATE_NEW_PROCESS_GROUP` and send
  `CTRL_BREAK_EVENT`; the scans' safe stop listens for SIGINT, so they'd need a SIGBREAK handler too. Under WSL2
  the Linux code works.
- **Installing tools.** The Setup tab installs ffmpeg and rubberband with Homebrew; without it, it shows
  `analysis.install_hint()`. Add a Windows hint (`winget install ffmpeg`; Rubber Band has Windows builds at
  breakfastquay.com/rubberband, needs 3.0+ for the R3 engine) or run winget from `_tool_install`.
- **Show in Explorer** (`web._show`) already uses `explorer /select,` on Windows. Under WSL2 it would take
  `explorer.exe` with the path converted by `wslpath -w`.

## Launcher

`Start Track Analyzer.command` is bash. Natively: a `Start Track Analyzer.bat` (or `.ps1`) that installs uv
(`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`), runs `uv sync` and `uv run dj-track-analyzer web`,
and sets `PYTHONUTF8=1`. Under WSL2: a `.bat` that calls `wsl -- ./"Start Track Analyzer.command"` in the repo.

## Lexicon

Lexicon has a Windows version (**verify**). `lexicon.py` needs:
- its database path for the backup before each load (now `~/Library/Application Support/lexicon/main.db`;
  on Windows probably under `%APPDATA%\lexicon`, **verify**);
- the location prefix it strips (now `/Volumes/<disk>`; Windows Lexicon likely sends `C:\…`, **verify**) so
  Lexicon's tracks match `collection.db` paths.
The Local API itself (localhost:48624) is the same; under WSL2 it's reachable from Linux on localhost.

## Order of work

1. Decide WSL2 or native (WSL2 unless there's a reason not to).
2. On a Windows machine with Traktor: copy `collection.nml` and `Traktor Settings.tsi` and note the `LOCATION` and
   `Browser.Dir.*` forms. Settle every **verify** above from real files.
3. Path mapping (`location_paths`, `mac_path`, collection search) and the Traktor-running check, which must fail closed.
4. Run `traktor --dry-run`, then a real write + `traktor --undo` on a copy of the collection, with Traktor closed
   and then open (it must refuse).
5. Launcher, Setup tab tool installs, Lexicon.
