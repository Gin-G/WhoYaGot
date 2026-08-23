---
status: active
progress: 74
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

An app that provides player tiles, this player, or that player, so that we can build a database of player preferences for users logged in via Google and overall across all users. It will start with NFL, and then expand to MLB, NHL, NBA, Soccer, Golf, etc. with selectable league tabs

Live at whoyagot.nickknows.net on NFL 2026, deployed by ArgoCD from main. The voting loop, both ladders, sign-in and the Android build all work, matchups come almost entirely from the 192 players anyone would draft, and a board now says which of its places your own picks have settled, reads against the crowd, and exports to the site you actually draft on. What is left is the other leagues, and the tuning that only shows up once a board has been used for a while.

## Todos

- [x] Deal same-position pairs from an Elo-weighted matchup engine
- [x] Rate players on two ladders, one global and one per signed-in user
- [x] Sync NFL rosters, teams and headshots from NFL-API, nightly by CronJob
- [x] Sign in with Google, and carry anonymous votes over to the account
- [x] Ship the global board, the personal board, and per-position filters
- [x] Package as a web app and an Android build, deployed by Helm and ArgoCD
- [x] Stop dealing camp bodies: cut each position to who will actually play
- [x] Score that cut on projections and last season's real production
- [x] Add a migration step, since create_all cannot alter an existing table
- [x] Compare already-ranked players so the top of a board actually sorts
- [x] Require three votes before a player is ranked on a personal board
- [x] Undo a pick, revise a pick, and read back the whole history
- [x] Filter picks to one player, to see who he was actually judged against
- [x] Cross positions when no position is pinned, matched on standing
- [x] Cut an Android release carrying the picks screen and cross-position play
- [x] Draw 85% of matchups from the 192 players anyone would actually draft
- [x] Show how far each of my ranks sits from the overall list, up or down
- [x] Colour that gap green where I am higher on a player and red where lower
- [x] Rank both lists over the same players, so the gap is disagreement not a floor
- [x] Export a board to MyFantasyLeague, Yahoo, Drafters or a spreadsheet
- [x] Page every list to its end instead of stopping at the first hundred
- [x] Put the W/YG mark on the launcher icon, the browser tab and the board tile
- [x] Green a rank once your own picks settle it, and count how many are set
- [ ] Confirm the Yahoo and Drafters column shapes against a real import
- [ ] Raise the consolidation share once real voting shows a board settling too slowly
- [x] Deal the pairs that would settle the most places, once a board is mostly set
- [x] Link rankings rows to their picks, the way the personal board does
- [ ] Watch whether a 50/50 cross-position split is the right mix in practice
- [ ] Revisit pool depth once cross-position votes show what positions are worth
- [ ] Let the global board be read as one list rather than four ladders
- [ ] Show a player's head-to-head record on his own card
- [ ] Add an MLB source adapter, the first league after NFL
- [ ] Add NHL, NBA, Soccer and Golf adapters once MLB proves the shape
- [ ] Ask NFL-API for expected games played, which the season endpoint lacks
- [ ] Decide what a matchup means when a player changes team mid-season
