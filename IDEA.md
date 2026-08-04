---
status: idea
progress: 0
---

# WhoYaGot

<!--
IdeaBRD parses this file. It is the source of truth for this idea's tile:
the app re-reads it on every open and commits its own edits back here, so
the shape below matters more than it looks. Anything the parser
(backend/app/ideafile.py) can't read is dropped silently.

  frontmatter  status: one of idea, active, paused, done. progress: 0-100.
               Any other key is ignored.
  # heading    The idea title (first H1).
  prose        Everything outside the Todos section becomes the tile's
               notes, shown on the board — so keep it short. Documentation
               written here is published, not filed away.
  ## Todos     That heading exactly (or "## To-Dos"); "## ToDo", "## TODO"
               and "## Tasks" do not match and the whole list is lost.
               Inside it, only "- [ ] open" / "- [x] done" lines survive:
               sub-headings and blank-line grouping are discarded, and a
               wrapped item is cut at the line break, so keep each to-do on
               one line. The next "## " heading ends the list.

To-dos are matched to the board by exact text, so rewording one replaces it
rather than editing it in place — expect a checked item to come back
unchecked if you reword it.

HTML comments are stripped on read, so this block never reaches the board.
-->

An app that provides player tiles, this player, or that player, so that we can build a database of player preferences for users logged in via Google and overall across all users

## Todos
