# DJ Track Analyzer

Local music analysis for a DJ's Mac: BPM, key, subgenre, mood, your own Traktor colour scale and a hype score, synced into **Traktor Pro 4** (and optionally Lexicon), plus an MCP server so a local LLM can search your collection. Fully offline, no length limit, free.

> **Already installed?** Day-to-day use is in **[docs/GUIDE.html](docs/GUIDE.html)** (`open docs/GUIDE.html`): what to run for each task, how to read the output, how to undo. This README is the full reference.

## What you get

For every MP3, WAV, FLAC, AIFF or M4A:

| | |
|---|---|
| **BPM** | A whole number, folded into 85–220 (a 170 BPM track heard as 85 is reported as 170). |
| **Key** | Key name plus **Camelot** code (8A, 11B, …), the wheel DJs use for harmonic mixing. |
| **Loudness** | Integrated **LUFS** (overall loudness), loudness range, and an energy curve through the track. |
| **DJ subgenre** | 42 DJ genres (Acid Trance, Hard Trance, Progressive Trance, Techno, Melodic House & Techno, Psytrance, …), top 3 with scores. No training needed. |
| **Discogs styles** | The raw top 5 of the 400 styles the genre models know. |
| **Mood, instruments, vocals** | Aggressive / happy / party / relaxed / sad, the strongest instruments, and how much of the track has a voice. |
| **Colour** | A Traktor colour for uncoloured tracks, learned from the tracks you've already coloured (Traktor's 7 colours read as a scale, Red … Magenta). |
| **Hype** | 1–10 within your collection, from the rave sound and energy. |
| **DJ mixes** | Files over 12 minutes get a timeline in 2-minute segments. |

When a track is in your Traktor collection, Traktor's own BPM and key are stored too, and they win for search, mix suggestions, hype filters and tag writes (you may have fixed the beatgrid by hand).

## Contents

1. [Install](#1-install-one-time)
2. [Scan your collection](#2-scan-your-collection)
3. [Genres in your files and in Traktor](#3-genres-in-your-files-and-in-traktor)
4. [Colours: learned from your colour-coding](#4-colours-learned-from-your-colour-coding)
5. [Hype (1–10)](#5-hype-110)
6. [Your catalogue at your play tempo](#6-your-catalogue-at-your-play-tempo-tempo-view)
7. [How the analysis works](#7-how-the-analysis-works)
8. [Ask a local LLM](#8-ask-a-local-llm-lm-studio-open-webui)
9. [Optional: train your own genres](#9-optional-train-your-own-genres)
10. [All commands](#10-all-commands) · [Settings](#settings) · [Project layout](#project-layout) · [Good to know](#good-to-know)

Every command runs from the project folder and starts with `uv run dj-track-analyzer` (it used to be `uv run server.py`; see [Project layout](#project-layout)). Anything that changes your files or Traktor has a `--dry-run` that shows what would happen and changes nothing.

---

## 1. Install (one time)

Open **Terminal**:

```bash
# 1. Install uv (Python manager). Skip if `uv --version` already works.
curl -LsSf https://astral.sh/uv/install.sh | sh
#    then close and reopen Terminal

# 2. Go to the project folder (wherever you cloned or unpacked it)
cd ~/dj-track-analyzer

# 3. Install everything: Python 3.11 + Essentia, about 400 MB
uv sync

# 4. Download the models: a few hundred MB, mostly MAEST
uv run dj-track-analyzer setup              # --no-maest: smaller, EffNet-only genres

# 5. Only for the tempo view (section 6)
brew install rubberband
```

Test it on a track:

```bash
uv run dj-track-analyzer analyze ~/Music/some-track.mp3
```

Under `genre_basis` it should say `"models": "EffNet + MAEST"`. If it says only `EffNet`, the reason is next to it under `maest`.

- **Model server unreachable?** `setup` tries a few ways, then prints a download link for each file it couldn't get. Open them in a browser, drop the files into `data/models/`, and run `setup` again to confirm.
- **Speed.** The first run takes a few extra seconds while TensorFlow loads; after that a typical track takes about 10–15 seconds on an M1 Pro Mac (MAEST is about half of that).
- **Requirements.** Apple Silicon with macOS 11 or newer, or an Intel Mac with macOS 14 or newer.

---

## 2. Scan your collection

```bash
uv run dj-track-analyzer scan --traktor            # every track in your Traktor collection
uv run dj-track-analyzer scan ~/Music/Incoming     # folders (and their subfolders)
uv run dj-track-analyzer scan --traktor ~/Music/Incoming   # both
```

`--traktor` reads Traktor's `collection.nml` and analyses exactly the tracks Traktor knows, wherever they're stored. It lists tracks Traktor knows but whose files are missing (moved, or on a disconnected drive).

**Skipped automatically:** Traktor's bundled samples, your Traktor recordings and sample/loop folders (read from Traktor's settings, so custom locations count), hidden folders and macOS `._` files.

- **Resumable.** Ctrl-C any time and run the same command again. Later runs only analyse new or changed files and drop deleted ones. Tag edits (by this app or another tagger) don't count as changes.
- **Parallel.** About half your CPU cores, at most 5 workers. Each holds the models in memory (1.5–2.5 GB with MAEST), so 32 GB is plenty.
- **Time.** About 20 seconds per track per worker; on an M1 Pro, 470 tracks took 33 minutes with 5 workers.

| Option | What it does | Default |
|---|---|---|
| `--traktor` | Scan every track in Traktor's collection | off |
| `--nml <path>` | Use another `collection.nml` | newest `~/Documents/Native Instruments/Traktor */` |
| `--exclude <folder>` | Leave a folder out; repeat for several. Earlier results from it are removed | none |
| `--include-recordings` | Also scan your Traktor recordings and samples | off |
| `--workers N` | Parallel analysers | half your cores, max 5 |
| `--rescan` | Analyse everything again, even unchanged files (slow; some updates need it) | off |
| `--write-tags genre` | Tag the files right after scanning (same fields as `tag --fields`) | off |
| `--csv <file>` | Write the spreadsheet somewhere else | `data/collection.csv` |

**Results:**
- `data/collection.csv`, a spreadsheet for Numbers or Excel (column guide in [GUIDE.html](GUIDE.html#results)). Write it again any time with `uv run dj-track-analyzer export [file]`.
- A database that the hype, colour and LLM tools read.
- `uv run dj-track-analyzer stats`: tracks per genre with average BPM, common keys, a BPM histogram, tracks per colour.

---

## 3. Genres in your files and in Traktor

### Write genres into the files' tags

Uses the saved scan; nothing is analysed again.

```bash
uv run dj-track-analyzer tag --multi --dry-run     # 1. preview "old genre → new genre", changes nothing
uv run dj-track-analyzer tag --multi               # 2. write the genre tag
```

| Option | What it does | Default |
|---|---|---|
| `tag <folder>` | Only files in that folder | everything scanned |
| `--multi` | Tracks between two genres get both: `Acid Trance; Hard Trance` | off |
| `--multi-ratio 0.7` | With `--multi`: a runner-up needs at least this share of the top score | 0.7 |
| `--max-genres 3` | With `--multi`: most genres per track | 3 |
| `--fields genre,bpm,camelot` | Also write BPM and key. Fields: `genre`, `bpm`, `key` (Am, F#…) or `camelot` (8A…), not both | `genre` |
| `--min-score 0.3` | Skip weak guesses (see `genre_score` in the CSV); those keep their current genre | 0 |
| `--use-my-genre` | Write your trained genres instead (section 9) | off |
| `--dry-run` | Preview the first 15 changes | off |

With `--multi`, clear-cut tracks keep one genre, and a runner-up that overlaps a chosen genre (Hard Trance + Trance) is left out so Smartlists can still tell them apart. **Navidrome** splits on `;`, lists the track under each genre, and picks the change up on its next library scan.

**Safety.** Before the first change to each file, its original genre, BPM and key tags are saved. Files that changed since they were scanned are skipped. Running `tag` again only touches files whose tags differ.

**Undo:**

```bash
uv run dj-track-analyzer untag --dry-run
uv run dj-track-analyzer untag                  # everything
uv run dj-track-analyzer untag ~/Music/X        # one folder
```

### Put genres into Traktor and build genre Smartlists

Traktor keeps its own copy of every track's tags in `collection.nml`, so new file tags don't reliably show up on their own. `traktor` edits the collection directly.

> **Quit Traktor first.** It rewrites the collection when it closes, which would undo the change, so the command refuses while Traktor is running.

```bash
uv run dj-track-analyzer traktor --dry-run         # preview
uv run dj-track-analyzer traktor                   # do it, then start Traktor
```

What it changes, and nothing else (cue points, beatgrids, play counts and your playlists stay byte-for-byte the same):
- **Genre** of every scanned track in the collection, set to the file's genre tag (so run `tag` first).
- **Colour** of tracks that have none yet, once you've trained a colour model (section 4). Colours you set are never changed.
- A playlist folder **Genres (Track Analyzer)** with one **Smartlist** (a saved search that updates itself) per genre, e.g. *Hard Trance* = Genre contains "Hard Trance". Only for this app's genre names and your trained ones; a shop tag like "melodic techno, indie dance" doesn't get a Smartlist. Names inside other names are handled: *Trance* excludes Acid/Hard/Tech/Progressive Trance and Psytrance, *Techno* excludes Acid/Hard/Dub/Industrial Techno and Melodic House & Techno, *Hardcore* excludes Happy Hardcore.

Each run recreates that folder, so keep customised copies of a Smartlist outside it.

| Option | What it does | Default |
|---|---|---|
| `--dry-run` | Preview only | off |
| `--undo` | Restore `collection.nml` from before the last run; run again to step back further | |
| `--undo --force` | Restore even though Traktor saved the collection since (loses what Traktor saved: plays, cues, edits) | |
| `--smartlists-only` / `--no-smartlists` | Only rebuild the Smartlists / only update genres | |
| `--no-colors` | Don't colour uncoloured tracks | |
| `--color-min-confidence 0.3` | Only colour the more reliable guesses | 0 |
| `--overwrite-colors` | Also replace colours you set yourself. Not recommended | off |
| `--nml <path>` | Another collection | newest Traktor folder |

Before every change it saves `collection.nml.before-track-analyzer-<date-time>` next to the collection, and it checks the result is valid before saving.

> **Tested with Traktor Pro 4.5:** Traktor opens and saves a collection edited this way, and the genre Smartlists show the right tracks.

### After editing `dj_genres.json`

```bash
uv run dj-track-analyzer regenre      # genres again from the saved scores, in seconds; updates the CSV
```

Your files and Traktor only change when you then run `tag --multi` and `traktor`.

---

## 4. Colours: learned from your colour-coding

If you colour-code tracks in Traktor, the app learns your system from the tracks you've already coloured and suggests colours for the rest. It reads Traktor's 7 colours as one ordered scale:

**Red** (1) → **Orange** → **Yellow** → **Green** → **Blue** → **Violet** → **Magenta** (7)

It works best when your colours mean something that runs in that order. The labels and the LLM tools assume Red = hardest/darkest and Magenta = softest/prettiest; the model itself just learns whatever order you use.

```bash
uv run dj-track-analyzer scan --traktor           # 1. analyse your Traktor tracks
uv run dj-track-analyzer colors train             # 2. learn your scale (only reads Traktor's files)
```

`colors train`:
- **First run:** a "deep listening" pass over all scanned tracks: MAEST's inner representation (texture, atmosphere, melody) plus mood, instrument and vocal scores. Cached; later runs take about a minute.
- Tries several models and keeps the one with the lowest error *averaged per colour*, so Red and Magenta count as much as the crowded middle. All scores are measured on tracks the model didn't train on.
- Prints a colour-scale check (BPM, loudness, aggressiveness per colour), the instruments that change most from Red to Magenta, and the tracks whose sound disagrees most with your colour.

**How good is it?** That depends on how consistent your colours are and how much they follow the sound. On a test collection of about 470 house/techno/trance tracks (Red = hard … Magenta = pretty), it was off by **1.17 colours** on average (always guessing the middle colour: 1.63) and right or one step off **67%** of the time. Neighbouring colours were close to a coin flip from the sound alone; the two ends were clearly apart. `colors train` prints these numbers for your collection. Retrain whenever you've coloured more tracks.

After training, every scan predicts a `color`, a `position` (5.4 = Blue leaning Violet) and a `confidence`: how often tracks placed there really had that colour. Most tracks are 0.2–0.3.

### The colour commands

| Command | What it does | Traktor |
|---|---|---|
| `colors train` | Learn your scale (above) | can stay open |
| `colors apply` | Scan new Traktor tracks, predict their colours, colour only the uncoloured ones | **closed** (except `--dry-run`) |
| `colors review` | The tracks whose sound disagrees most with your colour, judged by a model that never saw that track's colour | can stay open |
| `colors review --apply` | Recolour only the clearest disagreements | **closed** (except `--dry-run`) |
| `colors explain` | What each colour means in your collection (below) | can stay open |

| Option | Works with | What it does | Default |
|---|---|---|---|
| `--dry-run` | `apply`, `review --apply` | Show which colours would be set | off |
| `--min-confidence` | `apply` / `review --apply` | Only set guesses at least this reliable | 0 / 0.75 |
| `--min-gap 2.5` | `review --apply` | How many colours away from yours a track must sound | 2.5 |
| `--yes` | `review --apply` | Recolour every qualifying track without asking about each one | off |
| `--workers N` | `train`, `explain`, `apply` | Parallel workers for the deep listening pass | half your cores, max 5 |
| `--no-deep` | `train` | Skip the MAEST/mood/instrument features (faster, less accurate) | off |
| `--json` | `explain` | Raw numbers instead of tables | off |
| `--nml <path>` | all | Another collection | newest Traktor folder |

`review --apply` asks about each track first (yes / no / all the rest / cancel); `--yes` skips the questions, and they're skipped anyway when the input isn't a terminal. It skips tracks you've recoloured since training. `apply` and `review --apply` make the same backup as `traktor`, so **undo** is `traktor --undo` (Traktor closed).

**`colors explain`** (first run adds about 10 minutes of analysis) shows, per colour: approachability, moods, instruments, vocals, drop height, intro length, breakdowns, BPM, loudness, key, length, median plays and share of purchased tracks, each with its correlation with your scale. Then your playlists sorted hard → pretty, how often each colour is played in the first, middle and last third of your sets (from Traktor's History), and how consistent each artist's colours are.

---

## 5. Hype (1–10)

How hype a track is, ranked within your collection: 10 = more hype than 90% of your tracks. Half the score is the "rave" sound (trance, hard trance, hands-up, hardstyle rather than deep or tech house), half is energy (loudness, party and aggressive moods vs relaxed). On a test collection of about 470 house/techno/trance tracks, it matched the star ratings well enough to sort by, but not well enough to guess stars. The style half favours trance and hard dance, so it suits those collections best.

```bash
uv run dj-track-analyzer hype                                # most hype first
uv run dj-track-analyzer hype --least                        # chill first
uv run dj-track-analyzer hype --bpm 126 --key 8A --colour Yellow
uv run dj-track-analyzer hype --gems                         # hype 8+ but 4 stars or fewer, or played at most once
```

| Option | What it does | Default |
|---|---|---|
| `--least` | Chill end first | off |
| `--colour Red` | Only this colour (yours, else predicted) | all |
| `--bpm 126` | Only tracks near this BPM | all |
| `--bpm-tolerance 4` | BPM window in % | 4 |
| `--key 8A` | Only tracks that mix with this Camelot key | all |
| `--gems` | Very hype but few stars or plays | off |
| `--limit 50` | How many tracks to show | 25 |
| `--json` | Raw output | off |

### Hype in Traktor's Comment 2

> **Quit Traktor first.**

```bash
uv run dj-track-analyzer hype --traktor --dry-run      # preview
uv run dj-track-analyzer hype --traktor                # write "Hype 08" into Comment 2
uv run dj-track-analyzer hype --traktor --remove       # take it out again (this is the undo)
```

It's added after any text already in Comment 2 ("Check intro" becomes "Check intro · Hype 08"); re-running only updates the Hype part. Your normal Comment field is never touched. In Traktor, show the **Comment 2** column and sort by it. Because hype is relative, it can shift a step when you add many tracks, so re-run after big additions.

---

## 6. Your catalogue at your play tempo (tempo view)

If you play a set at one tempo with key lock, `tempo` stretches every scanned track to that tempo with [Rubber Band](https://breakfastquay.com/rubberband/) (pitch kept, like key lock) and analyses it again: genre, moods, colour and hype. Your normal results are never touched.

**Pick any tempo.** The default is 145; add `--bpm 140` (or any tempo) to `scan`, `report`, `export`, `nml`, `refresh` and `load`. Each tempo is a separate view with its own data in `data/at-<bpm>/`, so several can exist side by side; only one can be loaded at a time, and `native` switches back whichever one is. The examples below use the default.

```bash
uv run dj-track-analyzer scan --traktor              # new tracks first
uv run dj-track-analyzer tempo scan                  # about 1 hour the first time; resumable, then only new tracks
uv run dj-track-analyzer tempo report                # what changes at that tempo: genres, colours, hype
uv run dj-track-analyzer tempo export                # at-<bpm>/collection.csv
uv run dj-track-analyzer tempo nml                   # at-<bpm>/collection.nml, a standalone copy
uv run dj-track-analyzer tempo refresh               # redo genres, colours, hype from the cache (seconds)
uv run dj-track-analyzer tempo status                # which view is loaded where
```

Run `tempo refresh` after editing `dj_genres.json` or retraining colours.

### Switch Traktor to the view and back

> **Quit Traktor first** for `load` and `native`.

```bash
uv run dj-track-analyzer tempo load --dry-run        # preview
uv run dj-track-analyzer tempo load                  # switch Traktor to the view
uv run dj-track-analyzer tempo native                # switch back (this is the undo)
```

While loaded, Traktor shows per track:
- **Genre**: the genres heard at the view tempo.
- **Colour**: *your* colour, moved by how far the model thinks the track shifts at that tempo (your Blue, one step harder → Green). Uncoloured tracks stay uncoloured.
- **Comment 2**: the "Hype NN" part becomes the hype at that tempo; your own text there stays.
- **Smartlists**: "Genres (Track Analyzer)" is replaced by "Genres @145 (Track Analyzer)" (@ the view tempo).
- **Clock tempo**: set to the view tempo. Tracks follow it only with Sync on and the clock as master, which Traktor doesn't save.

`native` puts back only those fields, so cue points, plays, History and tracks added meanwhile carry over. If you changed a genre, colour or Comment 2 yourself while the view was loaded, `native` keeps your change and lists it under `kept`. The clock always goes back to your tempo.

Safety while the view is loaded:
- `traktor`, `traktor --undo`, `hype --traktor`, `colors apply` and `colors review --apply` refuse to run, so they can't mix your values into the view. `colors train` and `colors explain` refuse too: they read your colours from Traktor, and the view's shifted colours would skew them.
- `load` refuses while Traktor writes tags to your files (Preferences → File Management; `FileAccess.TagsSerialization` in Traktor Settings.tsi), because Traktor could write the view's genres into them and `native` only restores the collection. `--force` loads anyway.
- When a file changed since Traktor last read it, Traktor re-reads its tags on deck load and the file's genre and colour replace the view's. `load` sets each changed entry's modified stamp to the file's own time to prevent that; `native` puts the old stamp back. (Not yet confirmed in real Traktor.)
- Backups are named `collection.nml.before-tempo-view-…` and `Traktor Settings.tsi.before-tempo-view-…`; `traktor --undo` ignores them.

| Option | Works with | What it does | Default |
|---|---|---|---|
| `--bpm 140` | all but `native`, `status` | The view's tempo; each has its own `at-<bpm>/` folder | 145 |
| `--workers N` | `scan` | Parallel analysers | half your cores, max 5 |
| `--rescan` | `scan` | Analyse again even if cached | off |
| `--limit 30` | `report` | Tracks per list | 15 |
| `--json` | `report` | Raw output | off |
| `--out <file>` | `export`, `nml` | Write somewhere else | `at-<bpm>/` |
| `--dry-run` | `load`, `native` | Show what would change | off |
| `--force` | `load` | Load even while Traktor writes tags to files | off |
| `--lexicon` | `load`, `native` | Switch Lexicon too (below) | off |
| `--nml <path>` | all | Another collection | newest Traktor folder |

**How to read it.** The genre, mood and instrument models learned from millions of tracks, each at the tempo it was released at. Almost no house was released at 145, so the models have hardly ever heard a house track there: stretched to 145, a rolling house track sounds to them like the trance and psytrance they *did* hear at that tempo. Read the view as how the models hear the sped-up track, not as facts. The worst case, psytrance, is held back: in the view, psy only counts as much as the track already had at its own tempo, so most tracks that turn trancey become Trance or Progressive Trance instead. A Rubber Band pass without a tempo change gives the normal results, so the shifts come from the speed. Traktor's own stretcher sounds close to Rubber Band, not identical.

> **Tested with Traktor Pro 4.5:** a `tempo scan` of about 470 tracks; loading the view into Traktor, which opened and saved it; and `tempo native` putting back every value.

### Lexicon too

`--lexicon` on `load` / `native` switches [Lexicon](https://www.lexicondj.com) as well, for browsing and USB sync. Once: open Lexicon and turn on **Settings → Integrations → Local API**.

```bash
uv run dj-track-analyzer tempo load --lexicon --dry-run
uv run dj-track-analyzer tempo load --lexicon
uv run dj-track-analyzer tempo native --lexicon
```

Per track it changes Lexicon's **genre**, **colour** (moved by the same shift; shades other than Lexicon's 7 main colours are left alone), **comment** ("Hype NN" after your text, since Lexicon has no Comment 2) and **energy** (the hype at the view tempo, 1–10, replacing Lexicon's own), and adds a "Genres @145 (Track Analyzer)" smartlist folder. Its smartlists match a whole genre entry, so "Trance" doesn't catch "Hard Trance". If Traktor already has the view, `load --lexicon` only switches Lexicon; `native --lexicon` switches both back, restoring a field only if it still holds the view's value.

While Lexicon has the view, **don't sync Lexicon → Traktor or import from Traktor into Lexicon**. Syncing to a USB is fine; sync again after `native`.

**Backup.** Before every real `load --lexicon` / `native --lexicon`, Lexicon's library is copied to `data/lexicon-backups/` (newest 10). Last resort only, since it also undoes everything else changed in Lexicon since: quit Lexicon, copy the backup over `~/Library/Application Support/lexicon/main.db`, delete `main.db-wal` and `main.db-shm`.

> **Tested:** a real `load --lexicon` on about 480 tracks, with every smartlist holding exactly the expected tracks. `native --lexicon` has so far only been tested against a stand-in API.

---

## 7. How the analysis works

### Genre in three steps

1. **Find the main section.** The track is measured in ~1-second steps; anything more than 6 dB quieter than its loud parts (intros, outros, beatless breakdowns) is set aside. `main_section_share` says how much counted (0.7 = 70%).
2. **Ask two models.** **EffNet** (trained on 2 million+ tracks) listens to the whole main section; **MAEST** (4 million) to the three loudest 30-second blocks, usually the drops. Their style scores are blended 60% MAEST / 40% EffNet. If MAEST can't run, `genre_basis` says why and EffNet is used alone.
3. **Translate to DJ names** with `dj_genres.json`.

### The DJ names

The models use Discogs' style names, and some DJ terms don't exist there: "Acid Trance" comes out as **Acid** and **Trance** both scoring high. `dj_genres.json` maps styles to DJ names, each with the styles it needs and a typical BPM range:

```json
"Acid Trance": {"needs": [["Acid", "Acid House"], ["Trance", "Hard Trance", "Psy-Trance", ...]], "bpm": [135, 160]}
```

- A genre scores as high as its weakest required group, so Acid Trance needs an acid style *and* a trance style.
- Outside the BPM range a genre is scored down gradually, not excluded. Traktor's BPM is used when it has one.
- The top 3 come back as `dj_genre`.

There are 42 DJ genres, from Deep House to Speedcore. Left out on purpose: **Electro House** (the models give Discogs' 2010s "Electro House" to most modern melodic and peak-time house) and **Ambient** (stays part of Downtempo). Big Room, Future House, Afro House, Organic House, Melodic Techno, Future Bass and Hard Groove don't exist as Discogs styles; train them from examples instead (section 9).

**To change the genres:** copy `dj_genres.json` to `data/dj_genres.json` (so updates don't overwrite it), edit it, run `uv run dj-track-analyzer styles` to list all 400 style names and check for typos, then `regenre`.

### Moods, instruments and vocals

Small extra models, all downloaded by `setup`:
- **Mood:** aggressive, happy, party, relaxed, sad, each 0–1 over the main section.
- **Instruments:** 40 classes (synthesizer, bass, piano, pad, strings, bell, drum machine, …). Trained on Jamendo music rather than club tracks, so compare tracks rather than reading the numbers literally.
- **Vocals:** a voice/instrumental model over the whole track, since vocals often sit in breakdowns. `vocal_share` is the share of the track with a voice.
- **Approachability:** one number for hard ↔ pretty (higher = easier, prettier); it matches the colour scale best of all single measures.

These feed the colour model and `colors explain`, and appear in `analyze` and the CSV.

---

## 8. Ask a local LLM (LM Studio, Open WebUI)

### LM Studio

In LM Studio open the **Program** tab in the right sidebar, choose **Install → Edit mcp.json**, and add:

```json
{
  "mcpServers": {
    "track-analyzer": {
      "command": "/Users/YOUR_NAME/.local/bin/uv",
      "args": ["run", "--directory", "/Users/YOUR_NAME/dj-tools/track-analyzer", "dj-track-analyzer"]
    }
  }
}
```

- `which uv` in Terminal gives the exact path for `command`; LM Studio doesn't always see your shell's PATH.
- Use a model that's good at tool calling, such as Qwen3, Mistral Small or gpt-oss.

### Open WebUI

Start the server in HTTP mode and leave the Terminal window open:

```bash
uv run dj-track-analyzer serve --http                      # Open WebUI on this Mac
uv run dj-track-analyzer serve --http --host 0.0.0.0       # Open WebUI in Docker or on another machine
```

`--port` changes the port (default 8765). In Open WebUI: **Admin Settings → External Tools → +**, type **MCP (Streamable HTTP)**, with the URL for your setup:

| Open WebUI runs… | URL |
|---|---|
| on the Mac itself | `http://127.0.0.1:8765/mcp` |
| in Docker on the Mac | `http://host.docker.internal:8765/mcp` |
| on a NAS / another machine | `http://<your-mac's-LAN-IP>:8765/mcp` |

> **Note** The HTTP server has no password: only use `0.0.0.0` on your home network and never port-forward it. File paths are paths **on the Mac**, so a NAS can only analyse files the Mac can see (e.g. a share mounted at `/Volumes/music/`).

### What to ask

> How many acid trance tracks do I have, and what BPM are they mostly at?
>
> Find hard trance between 145 and 150 BPM that mixes harmonically with 8A.
>
> What could I play after "Insomnia"?
>
> Give me magenta acid trance around 145 BPM.
>
> Break down the mix at ~/Music/Mixes/acid-set.mp3: where does the tempo change?

Tip: in Finder, hold **Option**, right-click a file and choose **Copy "…" as Pathname**.

### Tools the LLM gets

| Tool | What it does |
|---|---|
| `search_collection(genre, bpm_min, bpm_max, camelot, harmonic, text, color, order, include_mixes, limit)` | Instant search of the scanned collection. `harmonic` adds compatible keys (±1 on the wheel, relative major/minor). `color` matches your colour, else the predicted one. `order`: bpm, genre, key, loudness, artist, recent or color. |
| `mix_suggestions(track, bpm_tolerance_pct=4, same_genre=true, limit=20)` | Tracks that mix with one you name: close BPM, compatible key, by default the same subgenre. |
| `collection_stats()` | Tracks per subgenre with average BPM, common keys, BPM histogram, tracks per colour. |
| `analyze_track(path, segment_seconds?)` | Full analysis of one file; long files get a mix timeline. |
| `analyze_folder(folder, limit=25)` | One line per track in a folder: BPM, Camelot, LUFS, top style, your genre. |
| `train_genres(folder)` | Same as `train`. Best for small sets; big ones can hit the chat app's tool timeout. |
| `list_genres()` | Which of your own genres are trained, and how many examples each has. |

---

## 9. Optional: train your own genres

Only for when the built-in names don't match how *you* split genres. The pretrained models still do the heavy lifting; you teach a small layer on top.

Make a folder with one subfolder (or one `.m3u` / `.m3u8` playlist) per genre; the name becomes the genre. Finder aliases aren't followed, so use copies or playlists.

```
~/Music/Genre Training/
├── Acid Trance/          20–50 tracks
├── Hard Trance/
├── Techno.m3u8           a playlist works too
└── Melodic House/
```

```bash
uv run dj-track-analyzer train ~/Music/"Genre Training"
```

You get an accuracy estimate per genre and the pairs it confuses most (`Hard Trance → Acid Trance: 3`). Add examples to weak genres and train again; analysis is cached, so only new tracks are processed. Pick clear, typical examples, keep genres balanced, and aim for 20 (usable) to 50+ (better) per genre. Afterwards `my_genre` appears next to `dj_genre`, and `tag --use-my-genre` writes it.

---

## 10. All commands

| Command | What it does | Changes |
|---|---|---|
| `setup [--no-maest]` | Download or check the models | model files |
| `analyze <file> [--segments 60]` | One track as JSON; mixes get a timeline (`--segments`: step in seconds) | nothing |
| `scan` | Analyse a collection (section 2) | app database, CSV |
| `stats` | Summary of the scanned collection | nothing |
| `export [file]` | Write the CSV again | CSV |
| `tag` / `untag` | Genres (and BPM/key) into file tags / put the old tags back | **your files** |
| `traktor` | Genres, colours and genre Smartlists into Traktor | **Traktor** (undo: `traktor --undo`) |
| `regenre` | Genres again from saved scores after editing `dj_genres.json` | app database, CSV |
| `styles` | List the 400 Discogs styles, check `dj_genres.json` | nothing |
| `colors train\|review\|explain\|apply` | Your colour scale (section 4) | `apply`, `review --apply`: **Traktor** |
| `hype` | Tracks by hype, with filters (section 5) | app database; `--traktor`: **Traktor** |
| `tempo scan\|report\|export\|nml\|refresh\|status\|load\|native` | The tempo view, 145 by default (section 6) | `load`, `native`: **Traktor** (and Lexicon) |
| `train <folder>` | Your own genres (section 9) | app files |
| `serve [--http] [--host] [--port]` | MCP server; stdio for LM Studio, HTTP for Open WebUI | nothing |

## Settings

Environment variables, in your shell or in an `"env": {}` block in `mcp.json`:

| Variable | Default | Meaning |
|---|---|---|
| `TRACK_ANALYZER_HOME` | `data` | Where models, caches, the database and your trained models live |
| `TRACK_ANALYZER_BPM_MIN` / `_MAX` | `85` / `220` | Window detected BPMs are folded into. Raise `_MAX` for speedcore |
| `TRACK_ANALYZER_MIX_THRESHOLD` | `720` | Seconds above which a file counts as a DJ mix |
| `TRACK_ANALYZER_MAEST` | `1` | `0` skips MAEST (faster, slightly less accurate genres) |
| `TRACK_ANALYZER_MAEST_BLOCKS` | `3` | How many of the loudest 30-second blocks MAEST hears |
| `TRACK_ANALYZER_MAIN_SECTION_DB` | `6` | How much quieter than the loud parts a stretch may be and still count toward genre |

## Project layout

```text
dj-track-analyzer/
├── README.md               this reference
├── docs/
│   ├── GUIDE.html          day-to-day guide (open in a browser)
│   └── IDEAS.md            features, ideas, what was tried
├── src/dj_track_analyzer/  the code (a Python package)
│   ├── cli.py              the `dj-track-analyzer` command
│   ├── mcp_server.py       MCP tools for LM Studio / Open WebUI
│   ├── analysis.py         models, cache and the analysis of one track
│   ├── collection.py       scan, database, CSV, tag/untag, search, mix suggestions
│   ├── traktor.py          collection.nml edits, Smartlists, undo
│   ├── colors.py           colour model (train, review, explain, apply)
│   ├── hype.py             hype score
│   ├── tempo.py            tempo view
│   ├── lexicon.py          Lexicon Local API
│   └── dj_genres.json      Discogs styles → DJ genre rules
├── logs/                   saved command output (`… 2>&1 | tee logs/scan.txt`), not in git
├── pyproject.toml, uv.lock
└── .claude/                Claude Code skills for this project
```

`python -m dj_track_analyzer …` works too. Your data (models, caches, databases, colour model) stays in `data`, outside the project folder.

**Coming from `uv run server.py`?** Run `uv sync` once, then use `uv run dj-track-analyzer` instead. In LM Studio's `mcp.json`, change the last item of `args` from `"server.py"` to `"dj-track-analyzer"` and the folder path to the project's new location (see [section 8](#8-ask-a-local-llm-lm-studio-open-webui)). Colour models trained before the move keep working.

## Good to know

- **Accuracy.** BPM and key are measured from the audio, as whole BPMs and one key per track. Our key agreed with Traktor's on about 57% of tracks in testing (relative major/minor is a common mix-up); neither is ground truth, and Traktor's wins where it has one. Genres and colours are model predictions: read the scores as confidence.
- **Files the analysis can't read.** Surround (5.1) files: make a stereo copy with `ffmpeg -i in.flac -ac 2 out.flac`.
- **Licences.** Essentia is AGPL; the Discogs models are CC BY-NC-SA (non-commercial). Personal use is fine.
- **Uninstall.** Delete this folder and `data`.
