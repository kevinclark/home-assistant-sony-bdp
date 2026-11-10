"""Remote entity for a Sony BDP-CE Blu-ray player.

Sends any remote-control button over the network (IRCC), not just the
handful the media_player entity covers: chapter skip, menus, navigation,
colour keys, number keys, ...

Usage from Home Assistant:

    action: remote.send_command
    target:
      entity_id: remote.ubp_x1100es
    data:
      command: Next          # or a list: [Down, Down, Confirm]

Command names come from the player's own command list (CERS
``getRemoteCommandList``), fetched once after pairing; if that fails, the
library's built-in table is used. The names currently known are exposed in
the entity's ``commands`` attribute. Matching is case-insensitive, and a few
friendly aliases (``ChapterNext``, ``PopUp``, ``Select``, ``Back``, ...) map
onto the device's names so scripts written for Harmony keep working.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

import requests
from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    RemoteEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from sony_bdp_ip import PairingRequired
from sony_bdp_ip.client import IRCC_CODES

from .const import CONF_MODEL, DOMAIN
from .coordinator import SonyBdpCoordinator

_LOGGER = logging.getLogger(__name__)

# Friendly names -> the device's IRCC names. Lets Harmony-style names
# ("ChapterNext", "PopUp", "DirectionUp", "Select") be used unchanged.
ALIASES: dict[str, str] = {
    "chapternext": "Next",
    "nextchapter": "Next",
    "skipforward": "Next",
    "chapterprev": "Prev",
    "prevchapter": "Prev",
    "previous": "Prev",
    "skipback": "Prev",
    "popup": "PopUpMenu",
    "popupmenu": "PopUpMenu",
    "menu": "PopUpMenu",
    "select": "Confirm",
    "ok": "Confirm",
    "enter": "Confirm",
    "back": "Return",
    "exit": "Return",
    "directionup": "Up",
    "directiondown": "Down",
    "directionleft": "Left",
    "directionright": "Right",
    "fastforward": "Forward",
    "subtitle": "SubTitle",
    "favorite": "Favorites",
    "open/close": "Eject",
    "openclose": "Eject",
    "powertoggle": "Power",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SonyBdpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SonyBdpRemote(coordinator, entry)])


class SonyBdpRemote(CoordinatorEntity[SonyBdpCoordinator], RemoteEntity):
    """Every button of the player's remote, over IP."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: SonyBdpCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        base_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{base_id}_remote"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, base_id)},
            name=entry.title,
            manufacturer="Sony",
            model=entry.data.get(CONF_MODEL) or "BDP-CE",
        )
        self._commands: dict[str, str] | None = None  # device name -> IRCC code
        self._device_commands: dict[str, str] = {}
        self._command_error: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.is_on:
            self.hass.async_create_task(self._async_load_commands())

    # --- state -----------------------------------------------------------

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.reachable)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "commands": sorted(self._known_commands()),
            "command_source": "device" if self._commands is not None else "builtin",
        }
        if self._device_commands:
            attrs["device_commands"] = self._device_commands
        if self._command_error:
            attrs["command_list_error"] = self._command_error
        return attrs

    # --- command table ---------------------------------------------------

    def _known_commands(self) -> dict[str, str]:
        return self._commands or IRCC_CODES

    async def _async_load_commands(self) -> None:
        """Fetch the device's own command list once; fall back silently."""
        if self._commands is not None:
            return
        try:
            commands = await self.hass.async_add_executor_job(
                self.coordinator.client.get_remote_commands
            )
        except Exception as err:  # noqa: BLE001 -- never break sending
            msg = f"{type(err).__name__}: {err}"
            if msg != self._command_error:
                _LOGGER.warning(
                    "%s: device command list unavailable, using built-in table (%s)",
                    self.entity_id,
                    msg,
                )
                self._command_error = msg
                self.async_write_ha_state()
            return
        self._command_error = None
        self._device_commands = dict(commands or {})
        if commands:
            # Keep built-in names the device list lacks.
            self._commands = {**IRCC_CODES, **commands}
            self.async_write_ha_state()

    def _resolve(self, name: str) -> str:
        """Map a user-supplied name onto a device command name."""
        known = self._known_commands()
        if name in known:
            return name
        lower = {k.lower(): k for k in known}
        key = name.strip().lower()
        if key in lower:
            return lower[key]
        alias = ALIASES.get(key)
        if alias and alias in known:
            return alias
        raise HomeAssistantError(
            f"Unknown command '{name}'. Known: {', '.join(sorted(known))}"
        )

    # --- actions ---------------------------------------------------------

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        await self._async_load_commands()
        names = [self._resolve(c) for c in command]  # validate all before sending
        repeats = kwargs.get(ATTR_NUM_REPEATS, DEFAULT_NUM_REPEATS)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        client = self.coordinator.client
        codes = self._known_commands()

        first = True
        for _ in range(repeats):
            for name in names:
                if not first and delay:
                    await asyncio.sleep(delay)
                first = False
                try:
                    await self.hass.async_add_executor_job(
                        client.send_ircc_code, codes[name]
                    )
                except PairingRequired as err:
                    raise HomeAssistantError(
                        "Player not paired yet - reconfigure the integration"
                    ) from err
                except requests.exceptions.RequestException as err:
                    raise HomeAssistantError(
                        f"Sending '{name}' to the player failed: {err}"
                    ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.coordinator.client.mac:
            raise HomeAssistantError(
                "No MAC address configured, so the player can't be woken over the network"
            )
        await self.hass.async_add_executor_job(self.coordinator.client.wake_on_lan)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self.is_on:
            return  # Power is a toggle; never wake a sleeping player by "turning it off"
        await self.async_send_command(["Power"])
        await self.coordinator.async_request_refresh()
