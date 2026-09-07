<!-- markdownlint-disable MD041 -->
# Sony BDP-CE Blu-ray Player for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kevinclark&repository=home-assistant-sony-bdp&category=integration)

IP control for Sony's **BDP-CE** family of Blu-ray players — developed and
tested against a **UBP-X700** — as a proper Home Assistant integration:
config flow, a real `media_player` entity, no YAML.

Sony never officially documented this API; it's the same protocol the
**Video & TV SideView** app used before its sunset (2027-03-30),
reverse-engineered against a real device and confirmed live at every step.
Full protocol write-up (every dead end included) and the underlying
standalone Python client (for non-HA use) live in a companion repo:
[**sony-bdp-ip**](https://github.com/kevinclark/sony-bdp-ip).

## What you get

- A `media_player` entity: on/off, play/pause/stop/eject, and whether
  content is actively being watched — all over the network, no IR blaster.
- Wake-on-LAN power-on from full standby.
- Disc format (e.g. "UHD BD-ROM") shown as the media title when a disc is
  loaded — see Limitations below for why it's format, not the movie's name.
- A config flow: add the integration, enter the host, pair with the PIN the
  player displays. No YAML required.

## Limitations (read this before filing an issue about it)

- **This device cannot distinguish playing from paused, and neither can
  this integration.** Checked directly against the device mid-pause —
  every status endpoint available returns identical results whether
  playing or paused. The entity's `playing` state means "content is on
  screen," full stop. See [sony-bdp-ip's protocol
  writeup](https://github.com/kevinclark/sony-bdp-ip/blob/main/docs/PROTOCOL.md)
  for everything that was tried and ruled out.
- **No disc/movie title or artwork is available either** — the API only
  ever reports physical format (BD/BD-ROM/UHD), never a title. `media_title`
  shows that format, not the movie's name. The player's own on-screen title
  most likely comes from metadata embedded on the disc itself, read
  locally by the player — not something any remote-control protocol
  (this one included) exposes externally.
- Pairing needs a display connected and on, at least the first time — the
  PIN shows as on-screen text over HDMI (this unit has no front-panel
  display to fall back on).
- Only tested against a UBP-X700. Other BDP-CE-era Sony Blu-ray players
  (and possibly some AV receivers/TVs of the same generation, which shared
  this control scheme) may work but haven't been verified.

## Installation

### HACS (recommended)

Click the badge above (opens HACS directly to this repository), or add it
manually:

1. HACS → the "⋮" menu → **Custom repositories** → add this repository's
   URL with category **Integration**.
2. Search for **"Sony BDP-CE Blu-ray Player"** in HACS and install it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/sony_bdp` into your `config/custom_components/`
directory and restart Home Assistant.

## Setup

### Player settings (do this first)

On the player itself, go to **Setup → Network Settings** and turn on:

- **Remote Start**
- **Auto Home Network Access Permission**

Both are off by default. Neither has been isolated as *strictly* required
(pairing was only ever tested with both on), but turn both on before
attempting setup below to rule them out as variables — see
[sony-bdp-ip's protocol notes](https://github.com/kevinclark/sony-bdp-ip/blob/main/docs/PROTOCOL.md)
for the full detail on what's confirmed vs. assumed here.

**Settings → Devices & Services → Add Integration → "Sony BDP-CE Blu-ray
Player."** You'll need:

- The player's IP address (a static/reserved DHCP lease is strongly
  recommended — this integration doesn't do discovery).
- Its MAC address, if you want power-on via Wake-on-LAN (check the
  player's network settings menu, or your router's client list).

The player will then show a PIN as on-screen text — make sure a display is
on and fed from the player before you submit the form. Enter that PIN on
the next screen to finish pairing.

## Contributing

Issues and PRs welcome — especially reports from other BDP-CE-family
devices (older/newer UBP/BDP models, AV receivers or TVs from the same
generation), and anyone who finds a real play/pause signal this project
missed (see the protocol writeup linked above before chasing that
particular white whale).

This repo vendors its own copy of the
[sony-bdp-ip](https://github.com/kevinclark/sony-bdp-ip) client
(`custom_components/sony_bdp/client.py`) rather than depending on it as a
published package, since it isn't on PyPI yet. Keep the two in sync — see
that file's docstring.

## License

[MIT](LICENSE)
