---
name: commit
description: Split the working tree's changes into commits that make sense, in this repo's commit style, with the docs brought up to date first. Use when the user types /commit or asks to commit their changes.
disable-model-invocation: true
---

# Commit the changes in sensible pieces

The user typing `/commit` (or asking to commit) is the go-ahead to commit. Don't push, and don't run `gh`: ask first
if that comes up. Any text after `/commit` ($ARGUMENTS) is guidance (e.g. "only the docs", "one commit", "no docs")
and wins over the rules below.

The git root is `dj-tools/`, one level above `track-analyzer/`. Run git from the root and use paths like
`track-analyzer/src/...`. Changes outside `track-analyzer/` belong to other tools: leave them alone unless the user
says to include them (the exception is `site/index.html`, the Pages landing page, when a change here affects it).

## 1. Look at everything

- `git status --porcelain`, `git diff --stat`, `git diff` (and `git diff --cached` if something is already staged),
  and read new untracked files.
- `git log -15 --format='%s%n%b---'` for the style.

## 2. Bring the docs up to date

Every behaviour change updates the docs in the same change. Before grouping anything, make sure the docs describe
what is about to be committed. Skip this only if $ARGUMENTS says so or the changes touch nothing a doc describes.

The `update-docs` skill (`track-analyzer/.claude/skills/update-docs/SKILL.md`) owns the rules for the docs: read
its doc table and style rules, and run its drift check from `track-analyzer/`:

```
uv run python .claude/skills/update-docs/scripts/doc_drift.py 2>/dev/null
```

Then, for each change, ask which doc covers it, grep for it, and read that whole section (never a whole guide):

- `README.md`: install, every command and option, how the analysis works, LLM setup, settings
- `docs/GUIDE.html`: the task-first guide for a DJ, not a programmer: plain words, no code names they'd never see
- `docs/IDEAS.md`: mark ideas done or tried-and-failed when a change settles them
- `CLAUDE.md`: architecture, design rules, verified facts, bugs not to reintroduce
- `CLAUDE.local.md` is gitignored: update it if useful, but it is never committed

The public docs stay impersonal: no personal paths, track names or one-person setups ("a test collection of about
470 tracks"). Fix anything missing, stale or wrong (old option names, defaults, numbers, removed features still
described). Check the docs against the code, not against memory, and keep the guide's contents list and links
working.

## 3. Group the changes

Group by what a change is *for*, not by file: one feature or fix per commit, with its code and docs together.
Docs-only corrections get their own commit.

Rules:
- If one file holds changes for two commits, split it by hunk: write the hunks for this commit to a patch in the
  scratchpad and `git apply --cached` it (no `git add -p`: interactive commands don't work here). Check with
  `git diff --cached` before committing.
- Never commit secrets (`.env`, API keys, tokens) or personal files (`CLAUDE.local.md`, `data/`, `logs/`,
  collection databases, Traktor `collection.nml` copies, local paths). If something like that shows up, leave it
  out and tell the user.
- Leave out anything that looks unfinished or accidental (scratch scripts, debug output, `__pycache__`) and mention
  it.
- When unsure whether two changes belong together, prefer fewer, coherent commits over many tiny ones.

## 4. Write the messages

Match the log:
- Subject: a plain sentence in the imperative saying what changed for the user ("Warn when MAEST is missing and
  show analyze progress", "Say when there's nothing to change; guard colour reads during tempo view").
  No `Area:` or conventional-commit prefix, no trailing period, ~50-80 chars.
- Body (for anything more than a one-liner): a blank line, then short `- ` bullets, one per user-visible change,
  naming the commands and options involved (`colors review --apply`, `--native`). End with a bullet for the docs
  if they changed ("Guide: How it works section, ...").
- Use a heredoc so the body keeps its formatting.

## 5. Commit and report

- Stage each group with explicit paths (`git add -- <files>` or `git apply --cached`), never `git add -A` / `.`,
  commit, and repeat. If a commit fails, fix the cause, restage and commit again; never `--no-verify`.
- Finish with `git status` (should be clean apart from what you left out on purpose) and `git log --oneline -<n>`.
- Tell the user: each commit's subject and files, what you changed in the docs, anything left uncommitted and why,
  and that nothing was pushed.
- If the guidance includes `compact` (e.g. `/commit compact`): end the report with a line to paste,
  `/compact <focus>`, where the focus says in one sentence what was just committed and what the next step is.
  Claude can't run `/compact` itself (it's a built-in command, only the user can type it).
