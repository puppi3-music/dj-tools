# DJ Track Analyzer: context for Claude

Local music-analysis tool for DJs: BPM, key/Camelot, subgenre, mood, a learned Traktor colour scale and a hype
score, synced into Traktor Pro 4 (optionally Lexicon), plus an MCP server for local LLMs (LM Studio, Open WebUI).
macOS, Python 3.11 via `uv`. Data dir: `data/` (`TRACK_ANALYZER_HOME`).

Docs: README.md (install + full reference), docs/GUIDE.html (task-first guide, self-contained, opened in a browser),
docs/IDEAS.md (features, ideas, tried-and-failed). Keep them in sync when commands, options or numbers change: the
`/update-docs` skill does this (`.claude/skills/update-docs/scripts/doc_drift.py` lists CLI options the docs miss).
Public docs stay impersonal: numbers come from "a test collection of about 470 tracks", no personal track names.

A gitignored `CLAUDE.local.md` may hold one developer's own setup, collection facts and history. Personal
details go there, never in this file.

## Working style
- Ask before design decisions; make new behaviour optional behind flags.
- Anything that writes to files, Traktor or Lexicon gets `--dry-run`, a backup and an undo path.
- Real Essentia models can't be downloaded in sandboxes; tests there use stand-ins for the TF models.
  Real-model behaviour is only verified by runs on a Mac.

## Files
Code is the package `src/dj_track_analyzer/` (relative imports; uv installs it editable). Run it as
`uv run dj-track-analyzer <command>` (entry point `cli:main`; no command = MCP over stdio) or `python -m dj_track_analyzer`.
Saved run output goes in `logs/` (gitignored). Skill scripts import `from dj_track_analyzer import …`.
- `analysis.py`: config, model loading, caches, `analyze_file`, custom genre training.
  `color_model()` aliases `sys.modules["colors"]` because bundles trained before the package move pickled
  `colors.BlockWeights` under that name.
- `cli.py`: argparse CLI (`main`). `mcp_server.py`: `build_mcp()` (mcp SDK **2.x**:
  `from mcp.server.mcpserver import MCPServer`) + `protect_stdout()`.
  Essentia (`essentia-tensorflow`, pinned dev1177 on Apple Silicon for macOS 11+ support).
- `collection.py`: `scan` (resumable, parallel spawn workers, SQLite `collection.db`), CSV export,
  `tag`/`untag` (mutagen; originals backed up in `original_tags` table), search, mix suggestions, `regenre`
  (genres again from cached scores + current dj_genres.json; reproduces scan exactly).
- `traktor.py`: `traktor` command. Surgical text edits of collection.nml (never a full XML rewrite),
  timestamped backups + `--undo` (refuses if the NML changed since our write, via a `.written-sha1` file next to
  the backup; `--force` overrides), refuses while Traktor runs. Sets INFO GENRE, INFO COLOR (only where
  missing unless `--overwrite-colors`), and a "Genres (Track Analyzer)" Smartlist folder, only for
  `known_genres()` = dj_genres.json names + trained genres (shop tags like "melodic techno, indie dance" would
  otherwise become ~100 Smartlists). `track_info()` reads Traktor's TEMPO BPM and MUSICAL_KEY (0-11 = C..B major,
  12-23 = C..B minor; INFO KEY is Open Key display text). Also `collection_tracks()` for `scan --traktor` and
  `recording_dirs()` (skips recordings + samples; `mac_path()` converts the .tsi's colon-style paths like
  `"Macintosh HD:Users:Shared:Traktor:Samples:"`).
- `colors.py`: `colors train|review|explain|apply`: learns a Traktor colour scale from already-coloured tracks.
- `hype.py`: `hype` command (find by hype, filters, gems, `--traktor` → Comment 2).
- `tempo.py`: `tempo` command, the catalogue as heard at one tempo (default 145, `--bpm` for any).
- `lexicon.py`: `tempo load/native --lexicon` via Lexicon's Local API.
- `dj_genres.json`: maps Discogs styles to DJ genre names (rules with "needs" groups + BPM range); a user copy in
  `data/dj_genres.json` wins.

## How the analysis works
- Decode once → stereo (loudness EBU R128), mono 44.1k (BPM via RhythmExtractor2013 multifeature, used raw,
  folded into 85–220; key via KeyExtractor `edma` → Camelot), mono 16k (models).
- **BPMs are whole numbers everywhere**: `analysis.round_bpm()` at measurement, Traktor's value as read
  (`load_traktor_info`), genre_bpm, the tempo view's source BPM, displays and CSVs (`collection.csv_value`).
  Traktor's own BPM/grid are never written.
- Traktor's BPM/key: `scan` stores them as `traktor_bpm` / `traktor_camelot` and passes Traktor's BPM to
  `analyze_file(genre_bpm=…)` for the genre rules. Search, mix suggestions, hype filters and BPM/key tag writes
  use COALESCE(Traktor's, ours) (`collection.BPM_SQL` / `CAMELOT_SQL`). The colour model uses our BPM.
  Our key matched Traktor's on 57% of a test collection; neither is ground truth.
- Genre: Discogs-EffNet (400 styles) averaged over the **main section** (windows within 6 dB of the loud part) +
  MAEST-519 on the 3 loudest 30 s blocks, blended 60% MAEST / 40% EffNet → `dj_genres.json` rules → `dj_genre`
  (top 3). Out-of-range BPM fades the score to 60% over `BPM_MARGIN` (3 BPM), not a cliff. The ×1.35 multi-group
  bonus only applies when different styles fill the groups. `label_scores`: MAEST-only styles (Neo Trance,
  UK Funky, …) stand in for EffNet at the track's EffNet/MAEST ratio over shared styles (MAEST runs ~1.3x higher).
- MAEST runs ONCE per track (`run_maest` → style scores + layer-7 embedding) via plain `TensorflowPredict` with
  our own input pipeline (`_maest_patches`: MusiCNN mels, (x − 2.0676)/(2·1.2683), 1876-frame patches, hop 1875,
  one patch per run: the graph has batch size 1). Verified identical to TensorflowPredictMAEST (max diff 2e-7).
  Cached in cache.db `deep` (`maest`, `maest_styles`), so rescans skip MAEST. A failure on one track doesn't
  disable MAEST for the rest of the worker; only load failures do.
- `tag --multi` writes "A; B" when the runner-up ≥ 70% of top and names don't overlap.
- Mood: EffNet heads mood_{aggressive,happy,party,relaxed,sad} (`model/Softmax`), optional downloads.
- Instruments: `mtg_jamendo_instrument` head (40 classes, main section) + `voice_instrumental` head (`vocals` mean /
  `vocal_share` >0.5, **whole track**); the tagger's own "voice" class is ~0.02 even on vocal club tracks.
  Cached in cache.db `deep.instruments`; `deep_features` adds them without recomputing MAEST.
- Extras (deep.extra JSON): approachability/engagement regression heads (`model/Identity`, whole track) +
  `energy_arc()` from short-term loudness.
- Files > 12 min are DJ mixes → timeline per 2-min segment.

### Colour
- Traktor INFO COLOR 1..7 = Red, Orange, Yellow, Green, Blue, Violet, Magenta. Treated as an ordered scale; labels
  and LLM tool docs assume Red = hardest/darkest … Magenta = softest/prettiest.
- `colors train` tries feature sets (incl. "descriptors weighted": moods, instruments, approachability/engagement,
  energy arc ×10 after standardising, `colors.WEIGHTED_SETS`) and picks by `average_error_per_colour` (macro),
  not the plain average, which rewards shrinking toward the middle. Baseline = always guess the median colour.
  Test collection (~470 tracks): 1.17 avg error vs 1.63 baseline, within-one 67%; neighbouring colours are near
  coin flips from audio, the ends are clearly apart.
- `confidence` = `analysis.color_confidence()`: kernel-smoothed (σ 0.3) share of CV tracks placed near that position
  that really had that colour (+5 pseudo-tracks of the overall rate). Bundles store `cv` (positions, truth);
  bundles without it → None (retrain). Typical 0.2-0.3. `review` uses within=1.
- `colors review --apply` recolours CV disagreements with gap ≥ 2.5 and within-one confidence ≥ 0.75
  (`traktor.set_colors`, skips tracks recoloured since). `read_traktor_colors` refuses while a tempo view is loaded (train, explain, apply). `colors apply`: scan --traktor (new only) → deep features
  for uncoloured → refresh predictions → `traktor.sync(update_genres=False, make_smartlists=False)`.
- `colors explain`: per-colour profile + playlists + History set position + artist consistency (read-only).

### Hype
- 1-10 decile within the scanned collection of (rank(rave styles) − rank(deep styles))/2 +
  (rank(lufs)+rank(party)+rank(aggressive)−rank(relaxed))/4. Rave = Trance, Hard Trance, Hands Up, Hardstyle,
  Tech Trance; deep = Deep Techno, Tech House, Deep House, Downtempo (EffNet activations from cache.db `emb`,
  never re-analyses). Stored in collection.db `hype`. Rationale: on a test collection, star ratings followed rave
  sound (+0.36) and energy (+0.30), not colour (−0.07) or drop size (~0); stars weren't predictable from audio
  (CV 0.56 vs 0.58 baseline), so there's a hype score instead of an auto-rating.
- `--traktor` writes "Hype NN" into **Comment 2 = INFO RATING** (stars = INFO RANKING, 51 per star), appended after
  existing text with " · "; `--remove` strips it (byte-identical round trip). Never touch INFO COMMENT.

### Tempo view (`tempo.py`)
- `analysis.stretch()` = Rubber Band CLI R3 (`brew install rubberband`, 4.0); `analyze_file(tempo=(src, target),
  genre_bpm=target)`. Source BPM = Traktor's, else ours. BPM is set to the target, not measured on stretched audio.
  The colour model gets the track's OWN BPM (feeding it the target alone moved colours −0.30 on average).
- Separate data in `data/at-<bpm>/` (cache.db with CACHE_VERSION + "|tempo-<bpm>", collection.db with
  extra `source_bpm`, `native_color_position`; `traktor_bpm` = target, so BPM_SQL gives the target). A changed source
  BPM drops that track's view cache. Models + colour model shared, never retrained on the view.
- The view's cache stores the STRETCHED duration: `analysis.STRETCH` {path: bpm/source_bpm} (filled by
  `tempo.view_db`) scales the expected length for `_recover_key`; `tempo scan` only updates size/mtime for files
  whose cache recovers instead of re-stretching them.
- Psy gate: sped up, the models hear Psy-Trance 0.6-0.9 in house that scores 0.0-0.1 at its own tempo (a tempo
  shortcut, not the BPM rules). In a view Psy-Trance/Goa are capped at 1.5 × the track's own-tempo psy
  (`tempo.view_genres`, in the scan loop and `tempo refresh`).
- `load`/`native` = carry-over swap: only INFO GENRE/COLOR/RATING, the genre Smartlist folder (@<bpm> folder takes
  the native folder's place, `traktor.swap_root_folder`), each changed entry's MODIFIED_DATE/TIME and the clock
  change. State in `data/tempo-loaded.json` as {VOLUME|DIR|FILE: {field: [yours, view]}}; `native`
  restores a field only if it still holds the view's value (clock always). Colour in view = user's colour +
  (view position − native position), both from the current model. Round trip byte-identical; real Traktor 4
  opened, rewrote and closed a loaded NML and `native` still matched every value.
- Backups: `collection.nml.before-tempo-view-…`, `Traktor Settings.tsi.before-tempo-view-…` (`traktor --undo`
  ignores them). `traktor.refuse_if_tempo_view` blocks sync/write_hype/set_colors/undo while loaded.
- Traktor re-reads file tags on deck load / Check Consistency when the file's mtime ≠ ENTRY MODIFIED_DATE/TIME
  (UTC date + seconds into that day); the file's genre/colour then replace INFO GENRE/COLOR (Comment 2 survives).
  So `load` stamps changed entries with the file's mtime (`traktor.file_stamp`, field "MODIFIED") and refuses while
  `FileAccess.TagsSerialization` ≠ 0 in Traktor Settings.tsi (`--force` overrides). Not yet confirmed in real Traktor.
- `load` sets `Status.Master Tempo` in the .tsi to the view BPM (`traktor.set_setting`). Traktor saves no deck Sync
  state and no clock-master state.

### Lexicon (`lexicon.py`)
- Local API localhost:48624/v1 (off by default; spec lexicondj.com/developer/api-docs.yaml): GET /tracks,
  PATCH /track, POST /playlist (type 1 folder, 3 smartlist), DELETE /playlists. Locations come as
  `/Volumes/Macintosh HD/Users/…` (prefix stripped to match).
- Changes genre, colour (same shift; non-main shades left alone), comment ("Hype NN" appended) and energy (view
  hype 1-10; empty energy is 0, not ""). Smartlists use StringRegExpMatch on whole "; " entries.
- State `data/tempo-loaded-lexicon.json` {lexicon id: {field: [yours, view]}}, written before editing.
  Before each real load/native: SQLite backup API copy of `~/Library/Application Support/lexicon/main.db`
  (ro URI, integrity_check) → `data/lexicon-backups/` (keep 10).
- Real load tested (smartlist counts exact); `native --lexicon` only against a mock API so far.

### Genre set
- 42 DJ genres. Progressive Trance is its own genre (126-145 BPM, taken out of Trance's needs).
- Deliberately NOT added: Electro House (the models give Discogs' 2010s "Electro House" to most modern melodic/
  peak-time house), Ambient (it went to a psytrance track in testing), Afro/Organic House as 2-style combos (matched
  nothing). Big Room, Future House, Afro House, Organic House, Melodic Techno, Future Bass, Hard Groove don't
  exist in Discogs: only via `train` with example folders.

## Traktor NML facts (verified on real Traktor 4 files)
- Smartlist node: `<NODE TYPE="SMARTLIST" NAME="X"><SMARTLIST UUID="hex"><SEARCH_EXPRESSION VERSION="1" QUERY="$GENRE % &quot;X&quot;"></SEARCH_EXPRESSION></SMARTLIST></NODE>`.
  `%` contains, `!%` not contains, `&` and, `|` or. Brackets reportedly don't work.
- LOCATION: `DIR="/:Users/:me/:Music/:" FILE="x.mp3" VOLUME="Macintosh HD"`; other drives → /Volumes/<VOLUME>.
- Real Traktor format uses explicit close tags and `standalone="no"`; keep edits textual.

## Bugs found and fixed (don't reintroduce)
- MAEST graph input is `melspectrogram`, NOT Essentia's default `serving_default_melspectrogram`: pass `input=`
  explicitly (`maest_input_name()`). Outputs: `PartitionedCall/Identity_13` = 519 predictions,
  `PartitionedCall/Identity_7` = layer-7 embeddings (768).
- Tag writes change file size/mtime → cache keys are re-keyed (`_rekey_cache`) so analysis isn't lost. For edits
  by Traktor, other taggers or file sync, a key miss falls back to the same path + `ver` = CACHE_VERSION + duration
  within 0.25 s of mutagen's audio length (`_recover_key`; mutagen vs decoded differ ≤ 0.05 s in practice).
- `refine_bpm` (line fit through the beat grid) was REMOVED: off-grid beats in breakdowns were counted as beats and
  pushed tempos up to 5 BPM high. Vs Traktor on 80 tracks: raw 96% within 1 BPM, with the fit 50%. A robust
  re-anchored fit was no better.
- Colour confidence used to be 1 − 2·|pos − round(pos)|, which gave the model's hedges (pos ≈ 4.0) confidence 1.0.
- Smartlist exclusions match the other genre's full name ("Techno" excludes "Melodic House & Techno").
- `scan --write-tags`: Traktor's BPM/key must be attached to the row before tags are written.
- `save_row` is `INSERT OR REPLACE` over `NAMES`: columns not in the scan result (`hype`, view-only columns) are
  wiped until recomputed.
- NFC vs NFD paths create duplicate rows (`_drop_decomposed_duplicates`); Syncthing `*.sync-conflict-*` copies and
  6-channel FLACs (Essentia's AudioLoader rejects them) need care.

## Tried, no gain (don't retry without a new idea)
- Colour model: hype as a feature; approachability/energy-arc alone over MAEST+sound; direct distortion measures
  (flatness, dissonance, crest, 2-5 kHz, clipping: flat across colours); MOSS-Music-8B 1-10 ratings (AUC 0.39-0.55
  vs 0.63 for the model, ~45 s/track).
