"""Sensor platform for the Fbot integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    KEY_AC_IN_FREQUENCY,
    KEY_AC_INPUT_POWER,
    KEY_AC_OUT_FREQUENCY,
    KEY_AC_OUT_VOLTAGE,
    KEY_AC_VERSION,
    KEY_BATTERY_PERCENT,
    KEY_BATTERY_S1_PERCENT,
    KEY_BATTERY_S2_PERCENT,
    KEY_BMS_VERSION,
    KEY_CHARGE_LEVEL,
    KEY_DC_INPUT_POWER,
    KEY_INPUT_POWER,
    KEY_OUTPUT_POWER,
    KEY_PANEL_VERSION,
    KEY_PV_VERSION,
    KEY_REMAINING_TIME,
    KEY_SYSTEM_POWER,
    KEY_TIME_TO_FULL,
    KEY_TOTAL_POWER,
    KEY_USB_A1_POWER,
    KEY_USB_A2_POWER,
    KEY_USB_C1_POWER,
    KEY_USB_C2_POWER,
    KEY_USB_C3_POWER,
    KEY_USB_C4_POWER,
)
from .coordinator import FbotCoordinator


@dataclass(frozen=True, kw_only=True)
class FbotSensorEntityDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with the coordinator data key."""

    data_key: str
    # Set of device_type strings for which this entity should be created.
    # None means the entity is created for every device type.
    supported_device_types: frozenset[str] | None = None


SENSOR_DESCRIPTIONS: tuple[FbotSensorEntityDescription, ...] = (
    FbotSensorEntityDescription(
        key="battery_percent",
        data_key=KEY_BATTERY_PERCENT,
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="battery_s1_percent",
        data_key=KEY_BATTERY_S1_PERCENT,
        name="Battery S1",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="battery_s2_percent",
        data_key=KEY_BATTERY_S2_PERCENT,
        name="Battery S2",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="ac_input_power",
        data_key=KEY_AC_INPUT_POWER,
        name="AC Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="dc_input_power",
        data_key=KEY_DC_INPUT_POWER,
        name="DC Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="input_power",
        data_key=KEY_INPUT_POWER,
        name="Input Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="output_power",
        data_key=KEY_OUTPUT_POWER,
        name="Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="system_power",
        data_key=KEY_SYSTEM_POWER,
        name="System Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="total_power",
        data_key=KEY_TOTAL_POWER,
        name="Total Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="charge_level",
        data_key=KEY_CHARGE_LEVEL,
        name="Charge Level",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="ac_out_voltage",
        data_key=KEY_AC_OUT_VOLTAGE,
        name="AC Output Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="ac_out_frequency",
        data_key=KEY_AC_OUT_FREQUENCY,
        name="AC Output Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="ac_in_frequency",
        data_key=KEY_AC_IN_FREQUENCY,
        name="AC Input Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="remaining_time",
        data_key=KEY_REMAINING_TIME,
        name="Remaining Time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="time_to_full",
        data_key=KEY_TIME_TO_FULL,
        name="Time to Full",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_a1_power",
        data_key=KEY_USB_A1_POWER,
        name="USB-A1 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_a2_power",
        data_key=KEY_USB_A2_POWER,
        name="USB-A2 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_c1_power",
        data_key=KEY_USB_C1_POWER,
        name="USB-C1 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_c2_power",
        data_key=KEY_USB_C2_POWER,
        name="USB-C2 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_c3_power",
        data_key=KEY_USB_C3_POWER,
        name="USB-C3 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="usb_c4_power",
        data_key=KEY_USB_C4_POWER,
        name="USB-C4 Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FbotSensorEntityDescription(
        key="ac_version",
        data_key=KEY_AC_VERSION,
        name="AC Firmware Version",
        entity_registry_enabled_default=False,
    ),
    FbotSensorEntityDescription(
        key="bms_version",
        data_key=KEY_BMS_VERSION,
        name="BMS Firmware Version",
        entity_registry_enabled_default=False,
    ),
    FbotSensorEntityDescription(
        key="pv_version",
        data_key=KEY_PV_VERSION,
        name="PV Firmware Version",
        entity_registry_enabled_default=False,
    ),
    FbotSensorEntityDescription(
        key="panel_version",
        data_key=KEY_PANEL_VERSION,
        name="Panel Firmware Version",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_type = coordinator.profile.device_type
    async_add_entities(
        FbotSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
        if description.supported_device_types is None
        or device_type in description.supported_device_types
    )


class FbotSensor(CoordinatorEntity[FbotCoordinator], SensorEntity):
    """A sensor entity for the Fbot device."""

    _attr_has_entity_name = True
    entity_description: FbotSensorEntityDescription

    def __init__(
        self,
        coordinator: FbotCoordinator,
        description: FbotSensorEntityDescription,
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
    def native_value(self):
        return (self.coordinator.data or {}).get(self.entity_description.data_key)
