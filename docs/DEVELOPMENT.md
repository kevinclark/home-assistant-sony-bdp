# Development notes

Two general Home Assistant `custom_component` gotchas turned up while
building this integration. Neither is specific to this device or its
protocol (see [sony-bdp-ip's protocol
writeup](https://github.com/kevinclark/sony-bdp-ip/blob/main/docs/PROTOCOL.md)
for that) — worth remembering for any future custom_component work.

1. **A config-entry reload does not re-import a custom_component's `.py`
   files.** Editing `coordinator.py` (or, before it moved to the
   `sony-bdp-ip` package, `client.py`) on disk and reloading the config
   entry (`POST /api/config/config_entries/entry/{id}/reload`) reruns
   `async_setup_entry` using whatever module object Python already had
   cached in `sys.modules` from the first load — it does **not** re-read
   the file. This produced a very convincing false negative: the
   coordinator polled every 10s and logged "success: True" the whole
   time, entity state looked plausible (`idle`), and yet none of the new
   logic was actually running — it was still executing the old code.
   **Fix: a full `ha core restart` after editing a custom_component's
   code**, not just a config-entry reload. Config-entry reloads are fine
   for picking up config *data* changes (like a renamed title), just not
   code changes.
2. **Renaming a live entity's `entity_id` via
   `config/entity_registry/update` can silently orphan its
   `DataUpdateCoordinator`'s polling loop.** The entity kept showing its
   last-known value indefinitely (`last_reported` frozen) with zero
   errors logged, until the config entry was reloaded again afterward.
   Rule: always follow an entity_id rename with a config-entry reload
   before trusting that entity's live state.
