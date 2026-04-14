"""Binary sensor platform for the Fbot integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    KEY_BATTERY_S1_CONNECTED,
    KEY_BATTERY_S2_CONNECTED,
)
from .coordinator import FbotCoordinator


@dataclass(frozen=True, kw_only=True)
class FbotBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Extends BinarySensorEntityDescription with the coordinator data key."""

    data_key: str


BINARY_SENSOR_DESCRIPTIONS: tuple[FbotBinarySensorEntityDescription, ...] = (
    FbotBinarySensorEntityDescription(
        key="battery_s1_connected",
        data_key=KEY_BATTERY_S1_CONNECTED,
        name="Battery S1 Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    FbotBinarySensorEntityDescription(
        key="battery_s2_connected",
        data_key=KEY_BATTERY_S2_CONNECTED,
        name="Battery S2 Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        FbotBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    entities.append(FbotConnectivitySensor(coordinator))
    async_add_entities(entities)


class FbotBinarySensor(CoordinatorEntity[FbotCoordinator], BinarySensorEntity):
    """A binary sensor entity derived from the coordinator data dict."""

    _attr_has_entity_name = True
    entity_description: FbotBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: FbotCoordinator,
        description: FbotBinarySensorEntityDescription,
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
        return super().available and self.entity_description.data_key in (
            self.coordinator.data or {}
        )

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get(self.entity_description.data_key)


class FbotConnectivitySensor(CoordinatorEntity[FbotCoordinator], BinarySensorEntity):
    """Tracks whether the BLE connection to the Fbot device is active."""

    _attr_has_entity_name = True
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_available = True

    def __init__(self, coordinator: FbotCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_connected"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name="Fbot Battery Station",
            manufacturer="Fbot",
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_connected
