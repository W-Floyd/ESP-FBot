"""Switch platform for the Fbot integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    REG_USB_CONTROL,
    REG_DC_CONTROL,
    REG_AC_CONTROL,
    REG_LIGHT_CONTROL,
    REG_AC_SILENT_CONTROL,
    REG_KEY_SOUND,
    KEY_USB_ACTIVE,
    KEY_DC_ACTIVE,
    KEY_AC_ACTIVE,
    KEY_LIGHT_ACTIVE,
    KEY_AC_SILENT,
    KEY_KEY_SOUND,
)
from .coordinator import FbotCoordinator


@dataclass(frozen=True, kw_only=True)
class FbotSwitchEntityDescription(SwitchEntityDescription):
    """Extends SwitchEntityDescription with Fbot-specific fields."""
    data_key: str
    register: int


SWITCH_DESCRIPTIONS: tuple[FbotSwitchEntityDescription, ...] = (
    FbotSwitchEntityDescription(
        key="usb",
        data_key=KEY_USB_ACTIVE,
        name="USB",
        register=REG_USB_CONTROL,
    ),
    FbotSwitchEntityDescription(
        key="dc",
        data_key=KEY_DC_ACTIVE,
        name="DC",
        register=REG_DC_CONTROL,
    ),
    FbotSwitchEntityDescription(
        key="ac",
        data_key=KEY_AC_ACTIVE,
        name="AC",
        register=REG_AC_CONTROL,
    ),
    FbotSwitchEntityDescription(
        key="light",
        data_key=KEY_LIGHT_ACTIVE,
        name="Light",
        register=REG_LIGHT_CONTROL,
    ),
    FbotSwitchEntityDescription(
        key="ac_silent",
        data_key=KEY_AC_SILENT,
        name="AC Silent",
        register=REG_AC_SILENT_CONTROL,
    ),
    FbotSwitchEntityDescription(
        key="key_sound",
        data_key=KEY_KEY_SOUND,
        name="Key Sound",
        register=REG_KEY_SOUND,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FbotSwitch(coordinator, description) for description in SWITCH_DESCRIPTIONS
    )


class FbotSwitch(CoordinatorEntity[FbotCoordinator], SwitchEntity):
    """A controllable switch entity for the Fbot device."""

    _attr_has_entity_name = True
    entity_description: FbotSwitchEntityDescription

    def __init__(
        self,
        coordinator: FbotCoordinator,
        description: FbotSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name="Fbot Battery Station",
            manufacturer="Fbot",
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.entity_description.data_key in (self.coordinator.data or {})
        )

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get(self.entity_description.data_key)

    async def async_turn_on(self, **kwargs) -> None:
        if self.is_on:
            return
        await self.coordinator.async_send_command(self.entity_description.register, 1)

    async def async_turn_off(self, **kwargs) -> None:
        if self.is_on is False:
            return
        await self.coordinator.async_send_command(self.entity_description.register, 0)
