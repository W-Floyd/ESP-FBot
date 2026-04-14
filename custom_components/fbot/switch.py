"""Switch platform for the Fbot integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FbotCoordinator
from .product_catalog import FEATURES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    features = FEATURES.get(
        coordinator.profile.product_id, {"states": [], "settings": []}
    )
    async_add_entities(
        FbotCatalogSwitch(coordinator, state)
        for state in features["states"]
        if state.get("input_index") is not None
    )


class FbotCatalogSwitch(CoordinatorEntity[FbotCoordinator], SwitchEntity):
    """A switch entity for a catalog-defined output state."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FbotCoordinator, state: dict) -> None:
        super().__init__(coordinator)
        self._state = state
        self._data_key = f"i_{state['input_index']}"
        self._attr_name = state["function_name"]
        self._attr_unique_id = f"{coordinator.address}_state_{state['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name="Fbot Battery Station",
            manufacturer="Fbot",
        )

    @property
    def available(self) -> bool:
        return super().available and self._data_key in (self.coordinator.data or {})

    @property
    def is_on(self) -> bool | None:
        val = (self.coordinator.data or {}).get(self._data_key)
        if val is None:
            return None
        return bool(val)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_send_command(self._state["holding_index"], 1)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_send_command(self._state["holding_index"], 0)
        self._attr_is_on = False
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when real data arrives."""
        self._attr_is_on = None
        super()._handle_coordinator_update()
