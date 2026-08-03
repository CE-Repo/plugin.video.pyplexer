# PyPlexer

Browse and play the video, music and photo libraries managed by your Plex Media
Server from inside Kodi.

> PyPlexer is **not** an official Plex add-on. It is not supported or endorsed
> by Plex.

- [Requirements](#requirements)
- [First run](#first-run)
- [What you get](#what-you-get)
- [Context menus](#context-menus)
- [Settings](#settings)
- [Adding Plex media to the Kodi library](#adding-plex-media-to-the-kodi-library)
- [Plex Companion](#plex-companion)
- [Up Next](#up-next)
- [TraktToKodi](#trakttokodi)

## Requirements

| | |
| --- | --- |
| Kodi | 21 (Omega) or newer |
| Server | Plex Media Server, reachable over the network |
| Account | Optional — a myPlex account is only needed for shared libraries, Plex Home users and access from outside your network |

PyPlexer pulls in `script.module.requests`, `script.module.pyxbmct` and
`script.module.infotagger`; Kodi installs them for you.

## First run

In most cases there is nothing to configure. PyPlexer discovers servers on the
local network over GDM and lists their libraries straight away.

If your server is not found:

1. Open *Settings → Server*
2. Set **Server Discovery** to `Manual`
3. Fill in **Primary Server Address** and **Port Number** (default `32400`)

To reach libraries shared with you, switch Plex Home users, or connect from
outside your network, sign in through *Settings → Server → Manage myPlex*. You
can sign in with your credentials or with a PIN shown on screen.

With several servers available, *Settings → Server → Select master server...*
picks the one used for myPlex Queue.

## What you get

**Libraries** — Movies, TV shows, music and photos, presented through the Plex
section views you already know: All, Unwatched, Continue Watching, On Deck,
Recently Added, Recently Released, Recently Viewed, By Collection, By Genre, By
Year, By Decade, By Director, By Starring Actor, By Country, By Content Rating,
By Rating, By Resolution, By First Letter, By Folder, and per-section search.

**Multiple servers** — Every discovered and shared server appears on the main
menu. *Combined Sections* merges the same content type across all of them into
one listing, and the all-servers rows (Recently Added, On Deck, search) span
every server at once.

**Main menu entries.** Everything below the library sections can be hidden in
*Settings → Look and Feel*, and several entries only appear once you are signed
in to myPlex.

| Entry | What it does | Shown when |
| --- | --- | --- |
| Combined Sections | One listing per content type, merged across servers | At least one section is listed |
| Playlists | Playlists stored on a server | Signed in to myPlex |
| PyPlexer Playlist | Builds a playlist from criteria you pick | Signed in to myPlex |
| myPlex Queue | Your myPlex watch later queue | Signed in to myPlex |
| Channels | Plex channels installed on a server | Always |
| Plex Online | Browse and install Plex channels | Always |
| Widgets | Paths intended for skin home-screen widgets | Always |
| Switch User | Change Plex Home user | Plex Home is enabled |
| Sign In / Sign Out | myPlex account | Always |
| Detect Servers | Re-runs discovery | Always |
| Manage Servers | Status, master server, certificate verification, custom access urls | Always |
| Clear Caches | Drops everything PyPlexer has cached | Caching is enabled |

Channels, Plex Online, Widgets and Playlists are per-server entries. By default
they only carry the server's name when more than one server is present; set
**Server name prefix on the main menu** to `Always` to label them regardless.

**Playback** — Direct play from local, SMB or AFP paths when the file is
reachable, falling back to streaming from the server. Watched state and
progress are reported back to Plex as you watch, so a resume point set in Kodi
is there on your phone.

**Better quality** — Before playback starts PyPlexer checks the other versions
of the title and offers the better ones in a dialog. It looks at the versions
of the item itself, at copies held as their own item elsewhere on the same
server - a *Movies 4K* library next to *Movies* - and, if you let it, at the
other servers of your account. Movies are matched by their Plex guid and, for
libraries scanned with different agents, by title and year; episodes by their
guid and otherwise through their show, season and episode number. The search
runs in parallel with a time limit, and the dialog only appears when the gain
is actually visible.

**Transcoding** — One always-on profile plus two optional ones, each with its
own quality, subtitle size and audio boost. When more than one profile is
enabled PyPlexer asks which to use. Transcoding can also be triggered
automatically for HEVC, for anything above 1080p, or for anything above 8-bit.

**Extras** — Skip-intro prompt driven by Plex's intro markers, song lyrics via
Plex's LyricFind integration, Up Next support for automatic next-episode
playback, a Plex Companion receiver so Plex apps can control Kodi, and Wake On
LAN for up to eleven servers.

## Context menus

**Inside PyPlexer listings** — Refresh, Go to (jumps to the parent season or
show), Add to playlist, Delete from playlist, Delete playlist, Mark as watched /
unwatched, Subtitles, Audio, Update library, and Delete. Delete is hidden unless
**Show the 'Delete' context menu** is enabled, and the whole set can be
suppressed with **Skip Context Menus** — both in *Settings → Look and Feel*.

**On library and widget items** — When Plex media has been scraped into the
Kodi library, a *PyPlexer* submenu adds *Transcoding*, *Mark as watched*
and *Mark as unwatched*, so watched state set in Kodi reaches the server.
On home-screen widgets backed by PyPlexer, the submenu provides *Open folder*
to open the widget's PyPlexer source. On TMDb Helper movie and TV-show widgets
it also adds *Add to Plex Watchlist* and *Remove from Plex Watchlist*. The
Watchlist actions resolve the item's
TMDb/IMDb/TVDb id, then update the Watchlist of the Plex account signed into
PyPlexer.

## Settings

| Category | Covers |
| --- | --- |
| Server | Discovery, manual address, HTTPS, myPlex, master server, Wake On LAN |
| Playback | Stream source, audio/subtitle selection, DVD, SMB overrides, intro skipping, lyrics, transcoding, better quality search |
| Look and Feel | Menus shown, season flattening, episode sorting, server name prefixes, Recently Added counts, context menus, Fanart.tv thumbs |
| Kodi Library | Which sections are exported to the Kodi library |
| Up Next | Up Next integration and its notification encoding |
| Companion Receiver | The Plex Companion listener and Kodi's web server credentials |
| Advanced | Playback monitor, artwork resolution, metadata and media flag skipping |
| Cache | Server and data cache toggles and TTLs, plus Clear Caches |
| Debug | Log level, log redaction, skip-intro dialog preview |

A few worth knowing about:

- **Stream from PMS** (*Playback*) — `Auto` plays the file directly when Kodi
  can reach the path and streams otherwise. Force streaming with `http`, or
  point PyPlexer at your own share with `smb` / `AFP`.
- **Audio and subtitle selector** (*Playback*) — `Plex Control` applies the
  track selection made in Plex; `Kodi Control` leaves Kodi's own preferences
  alone; `Never show subtitles` forces them off.
- **Search for a better quality before playback** (*Playback*) — compares the
  versions of the title and asks which one to play when a better one exists.
  Closing that dialog with Back or the X cancels playback.
  *Include other servers in the search* also asks the other servers of your
  account, and *Maximum search time* caps how long that may take. *Always show
  the version dialog* asks whenever more than one version exists, even when
  none of them is better - useful to check that the search is working.
- **Flatten TV Shows** (*Look and Feel*) — `Off`, `If only one season`, or
  `All seasons`.
- **Episode sort method** (*Look and Feel*) — `Kodi` sorts by season and
  episode, `Plex` keeps the order the server sends.
- **Prefer external thumbs and clearlogos** (*Look and Feel*) — uses localized
  wide artwork and transparent title logos for movies and TV shows. For both
  image types, the order is Fanart.tv in the preferred language, Fanart.tv in
  English, TMDb in the preferred language, TMDb in English, and finally Plex.
  Fanart.tv requires
  a [personal API key](https://fanart.tv/get-an-api-key/). The TMDb API key or
  Read Access Token is optional; without it the TMDb step is skipped. On
  Fanart.tv the image with the most likes in the requested language wins; TMDb
  chooses the best-rated matching backdrop or logo. `auto` uses Kodi's
  language, while a two-letter code such as `de` or `en` overrides it. API
  errors advance to the next fallback and results are cached for seven days.
  Thumbs are exposed as Kodi `landscape` artwork; poster views continue to
  display Plex's portrait poster. Plex listings are loaded server-side in
  pages of at most 100 entries, including libraries, collections, seasons,
  episodes, search results and channels. Watchlist and Discover keep their
  native provider behavior. Lists of up to 20 titles resolve missing artwork
  immediately; larger pages open from cache
  without waiting for external APIs. PyPlexer's service fills missing artwork
  in the background
  and refreshes an open PyPlexer list once the queue is complete.
- **Server name prefix on the main menu** (*Look and Feel*) — `Default` adds the
  server name only when more than one server is present, `Always` adds it even
  with a single server.
- **Data Cache TTL** (*Cache*) — how long listings are reused before PyPlexer
  asks the server again. Lower it if changes made in Plex take too long to
  appear.

## Adding Plex media to the Kodi library

PyPlexer can feed the Kodi video library so Plex content sits alongside your
local media and is visible to skins and other add-ons. Scraped items lose most
Plex-specific behaviour, so PyPlexer's own listings remain the richer way to
browse.

Add a video source pointing at one of these paths:

**Movies** — `plugin://plugin.video.pyplexer/library/movies/`

- Choose information provider: *Local information only*
- Movies are in separate folders that match the movie title: **disabled**
- Scan recursively: **disabled**

**TV Shows** — `plugin://plugin.video.pyplexer/library/tvshows/`

- Choose information provider: *Local information only*
- Selected folder contains a single TV show: **disabled**

Follow the [Adding video sources](https://kodi.wiki/view/Adding_video_sources)
wiki page, using the `plugin://` path above in place of steps 4–5 and choosing
*Local information only* at step 9.

Choose which sections are exported with *Settings → Kodi Library → Select
sections to include in library scans*; *Reset selected sections* clears the
choice.

## Plex Companion

The companion receiver lets Plex apps on your phone, tablet or desktop see Kodi
as a playback target and control it.

> Marked **experimental** in the settings. Changes to these settings need a Kodi
> restart to take effect.

1. Enable Kodi's web server: *Settings → Services → Control → Allow remote
   control via HTTP*
2. In *Settings → Companion Receiver*, set **Enabled**
3. Enter the same **Username**, **Password** and web server **Port** you set in
   step 1
4. Optionally change the **Device Name** (default `Kodi-PyPlexer`) and the
   listener **Port** (default `3005`)
5. Restart Kodi

Kodi then appears as a player in your Plex apps while the service is running.

## TMDb Helper

`resources/tmdbhelper/pyplexer.json` is a ready made player for
*The Movie Database Helper*. Copy it to

```
userdata/addon_data/plugin.video.themoviedb.helper/players/pyplexer.json
```

restart Kodi, and pick **PyPlexer** as the player - not *PyPlexer (Search)*,
which is the manual search and knows nothing about the year. TMDb Helper
remembers the player chosen for an item, so an item that was played with the
search entry before keeps using it until the default is cleared.

There is no fallback from the precise lookup to the search: a film the lookup
does not find is not played, rather than the wrong film being offered.

`PyPlexer.search -> Search: query=... year=... -> exact lookup` in `kodi.log`
shows what the player handed over. A line saying `plain lookup` means no year
arrived and the search cannot tell the films of that name apart.

The player hands the title over together with the data it already knows -
`year` for a film, `showtitle`, `season` and `episode` for an episode - and
PyPlexer resolves that to a single item instead of returning everything Plex'
full text search finds for the word.

TMDb Helper movie and TV-show widgets also expose *PyPlexer → Add to Plex
Watchlist* and *PyPlexer → Remove from Plex Watchlist* in Kodi's context menu.
Each action performs the selected operation for the focused title and reports
whether it was added, removed or was already present. The actions are available
on home-screen widgets, in Arctic Fuse 3 search results, and in its video
information dialog.

A film only counts as a match when its title matches exactly - checked against
the library title, the original title and the sort title - and its year fits.
A film of the same name from another year is a different film and is left out,
even when that means nothing is returned; only when no item carries the
requested year is a difference of one year accepted, because regions release a
film a year apart. Every copy of the right film is returned - a Full HD and a
4K item are two things to choose from - with the better quality first.

Without a year the search stays as broad as it always was - the add-on's own
search needs that - and only the order changes: exact title matches first, then
newest first.

## Up Next

With [Up Next](https://kodi.wiki/view/Add-on:UpNext) installed, PyPlexer offers
the next episode as one finishes.

Enable it in *Settings → Up Next*. If Up Next is not installed the settings
screen offers to install it; if it is installed but disabled, PyPlexer offers
to enable it. **Notification encoding** (`hex` or `base64`) only needs changing
if episode data does not reach Up Next.

## TraktToKodi

PyPlexer pairs with the TraktToKodi browser extension to play a title from
Trakt.tv straight on your Kodi box. Set the `Add-on ID` in your TraktToKodi
profile to `plugin.video.pyplexer`.

- **Chrome:** [Chrome Web Store](https://chrome.google.com/webstore/detail/trakttokodi/jongfgkokmlpdekeljpegeldjofbageo)
  · [source](https://github.com/anxdpanic/TraktToKodi-Extension/tree/chrome)
- **Firefox:** [AMO Gallery](https://addons.mozilla.org/en-US/firefox/addon/trakttokodi/)
  · [source](https://github.com/anxdpanic/TraktToKodi-Extension/tree/firefox)
