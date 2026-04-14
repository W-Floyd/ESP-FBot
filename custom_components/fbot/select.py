"""Select platform for the Fbot integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FbotCoordinator
from .product_catalog import FEATURES


def _option_label(value: int, unit: str) -> str:
    """Format a data_list integer as the string shown in the UI."""
    return f"{value} {unit}".strip() if unit else str(value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    features = FEATURES.get(
        coordinator.profile.product_id, {"states": [], "settings": []}
    )
    count = coordinator.profile.modbus_count
    async_add_entities(
        FbotCatalogSelect(coordinator, setting)
        for setting in features["settings"]
        if (
            setting["data_state"]
            and len(setting["data_list"]) > 1
            and setting.get("holding_index") is not None
            and setting["holding_index"] < count
        )
    )


class FbotCatalogSelect(CoordinatorEntity[FbotCoordinator], SelectEntity):
    """A select entity for a catalog-defined writable setting."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FbotCoordinator, setting: dict) -> None:
        super().__init__(coordinator)
        self._setting = setting
        self._data_key = f"h_{setting['holding_index']}"
        unit = setting.get("unit", "")
        options = [_option_label(v, unit) for v in setting["data_list"]]
        # Bidirectional maps between display label and raw register value.
        self._value_to_option: dict[int, str] = dict(zip(setting["data_list"], options))
        self._option_to_value: dict[str, int] = dict(zip(options, setting["data_list"]))
        self._attr_name = setting["function_name"]
        self._attr_options = options
        self._attr_unique_id = f"{coordinator.address}_setting_{setting['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name="Fbot Battery Station",
            manufacturer="Fbot",
        )

    @property
    def available(self) -> bool:
        return super().available and self._data_key in (self.coordinator.data or {})

    @property
    def current_option(self) -> str | None:
        raw = (self.coordinator.data or {}).get(self._data_key)
        if raw is None:
            return None
        return self._value_to_option.get(raw)

    async def async_select_option(self, option: str) -> None:
        value = self._option_to_value.get(option)
        if value is None:
            return
        await self.coordinator.async_send_command(self._setting["holding_index"], value)
        await self.coordinator.async_send_settings_refresh()
