"""Polling coordinator for a Sony BDP-CE device."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from xml.etree import ElementTree

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from sony_bdp_ip import SonyBdpClient

from .const import DIAL_APP, DIAL_PORT, DIAL_TIMEOUT, DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


@dataclass
class SonyBdpData:
    """Latest known state of the player."""

    reachable: bool
    viewing_content: bool
    disc_info: dict[str, str] = field(default_factory=dict)
    # Which signal(s) said content was up, for diagnostics.
    cers_viewing: bool = False
    dial_running: bool = False


class SonyBdpCoordinator(DataUpdateCoordinator[SonyBdpData]):
    """Polls for whether content is actively being watched, then whatever disc
    info is loaded. Treats connection failure as 'powered off'.

    Two independent signals are OR'd together:

    1. CERS ``getStatus`` -> a ``<status name="viewing">`` entry.
    2. DIAL ``GET :50202/apps/com.sony.videoplayer`` -> ``<state>running</state>``.

    **Why both, as of 2026-09-19.** ``viewing`` was documented (2026-09-07) as
    the confirmed signal, and DIAL was documented as having "the exact same
    granularity". Both claims were falsified live on 2026-09-19: a UHD BD-ROM
    played for over an hour, confirmed by the owner and corroborated by the
    projector reporting a 3840x2160/24p signal, while every ``getStatus``
    response across four sampling windows returned ONLY a ``disc`` entry and
    never ``viewing``. DIAL reported ``running`` throughout. The coordinator was
    verified to be polling normally the whole time (debug log, ~10 s cadence,
    success: True), so this is the device's answer, not a fetch failure.

    DIAL is therefore the signal that currently works. CERS ``viewing`` is kept
    in the OR because it costs nothing and self-heals if the device starts
    reporting it again -- but do not expect it to contribute. Suspected cause of
    the change: a player firmware update since 2026-09-07 (no firmware version
    was captured then, so there is no baseline to diff).

    Note DIAL is slightly broader than ``viewing`` was meant to be: it reads
    ``running`` from the disc's own top menu onward, not only during the
    feature. For "the disc is up, dim the room" that is the more useful line.

    Neither signal distinguishes play from pause -- that is not available
    anywhere on this device, see docs/PROTOCOL.md. AVTransport remains ruled
    out: re-tested 2026-09-19 during confirmed playback, still
    NO_MEDIA_PRESENT.

    The player drops off the network entirely in full standby (relying on
    Wake-on-LAN at the Ethernet frame level, no IP stack involved), so a
    connection failure on the CERS call is the expected, normal way we learn the
    player is off, not an integration error.
    """

    def __init__(self, hass: HomeAssistant, client: SonyBdpClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client

    def _dial_running(self) -> bool:
        """True if the player's video app is running. Needs no pairing.

        Any failure returns False rather than raising: the CERS call owns the
        reachable/powered-off determination, and DIAL must never be able to
        turn a working poll into an 'off' reading.
        """
        url = f"http://{self.client.host}:{DIAL_PORT}/apps/{DIAL_APP}"
        try:
            response = requests.get(url, timeout=DIAL_TIMEOUT)
            response.raise_for_status()
            state = ElementTree.fromstring(response.content).find(
                "{urn:dial-multiscreen-org:schemas:dial}state"
            )
            return state is not None and state.text == "running"
        except (requests.exceptions.RequestException, ElementTree.ParseError):
            return False

    async def _async_update_data(self) -> SonyBdpData:
        try:
            status = await self.hass.async_add_executor_job(self.client.get_status)
        except requests.exceptions.RequestException:
            return SonyBdpData(reachable=False, viewing_content=False)

        cers_viewing = "viewing" in status
        dial_running = await self.hass.async_add_executor_job(self._dial_running)

        return SonyBdpData(
            reachable=True,
            viewing_content=cers_viewing or dial_running,
            disc_info=status.get("disc", {}),
            cers_viewing=cers_viewing,
            dial_running=dial_running,
        )
