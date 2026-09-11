"""Sensor Entity Description for the Modbus Local Gateway integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.number import NumberEntityDescription, NumberMode
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.text import TextEntityDescription
from homeassistant.components.water_heater import WaterHeaterEntityDescription
from homeassistant.helpers.entity import EntityDescription

from .const import (
    CONV_BITS,
    CONV_MULTIPLIER,
    CONV_OFFSET,
    CONV_SHIFT_BITS,
    CONV_SUM_SCALE,
    CONV_SWAP,
    CONV_UNAVAILABLE_VALUES,
    IS_FLOAT,
    IS_SIGNED,
    IS_STRING,
    MAX_CHANGE,
    PRECISION,
    REGISTER_COUNT,
    ControlType,
    ModbusDataType,
    WaterHeaterRole,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(kw_only=True, frozen=True)
class UnusedKeysMixin:
    """Mixin for unused but allowed keys."""

    address: int | None = 0  # register_address
    size: int | None = 1  # register_count
    swap: str | None = None  # conv_swap
    sum_scale: list[float] | None = None  # conv_sum_scale
    multiplier: float | None = 1.0  # conv_multiplier
    offset: float | None = None  # conv_offset
    shift_bits: int | None = None  # conv_shift_bits
    bits: int | None = None  # conv_bits
    map: dict[int, str] | None = None  # conv_map
    unavailable_values: list[int] | None = None  # conv_unavailable_values
    flags: dict[int, str] | None = None  # conv_flags
    string: bool | None = False  # is_string
    float: bool | None = False  # is_float
    signed: bool | None = False  # is_signed
    control: str | None = ControlType.SENSOR  # control_type
    number: dict[str, int] | None = None  # min, max
    switch: dict[str, float] | None = None  # on, off
    water_heater: dict[str, Any] | None = None  # roles and settings


@dataclass(kw_only=True, frozen=True)
class ModbusRequiredKeysMixin:
    """Mixin for required keys."""

    register_address: int
    data_type: ModbusDataType


@dataclass(kw_only=True, frozen=True)
class ModbusEntityDescription(
    EntityDescription, ModbusRequiredKeysMixin, UnusedKeysMixin
):
    """Describes Modbus sensor entity."""

    register_count: int | None = 1
    conv_swap: str | None = None
    conv_sum_scale: list[float] | None = None
    conv_multiplier: float | None = None
    conv_offset: float | None = None
    conv_shift_bits: int | None = None
    conv_bits: int | None = None
    conv_map: dict[int, str] | None = None
    conv_unavailable_values: list[int] | None = None
    conv_flags: dict[int, str] | None = None
    is_signed: bool | None = False
    is_string: bool | None = False
    is_float: bool | None = False
    precision: int | None = None
    never_resets: bool = False
    control_type: str | None = ControlType.SENSOR
    max_change: float | None = None
    scan_interval: int | None = None

    def validate(self) -> bool:
        """Validate the entity description"""
        if not self._validate_string_and_float():
            return False
        if not self._validate_string_constraints():
            return False
        if not self._validate_float_constraints():
            return False
        if not self._validate_register_count():
            return False
        if not self._validate_max_change():
            return False
        if not self._validate_scan_interval():
            return False
        if not self._validate_bitfield():
            return False
        if not self._validate_unavailable_values():
            return False
        return True

    def _validate_unavailable_values(self) -> bool:
        """`unavailable_values` must be a list of whole numbers.

        They are matched against the raw register value - after any `bits` /
        `shift_bits` masking, but before `multiplier` and `offset`.
        """
        if self.conv_unavailable_values is None:
            return True
        if not isinstance(self.conv_unavailable_values, list) or not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in self.conv_unavailable_values
        ):
            _LOGGER.warning(
                "Unable to create entity for %s: %s must be a list of integers",
                self.key,
                CONV_UNAVAILABLE_VALUES,
            )
            return False
        return True

    def _validate_bitfield(self) -> bool:
        """Check constraints for writable bit fields.

        The merge assumes an unsigned value: a signed field has no well-defined
        representation once masked into part of a register.

        The geometry must also fit the register span, and a coil is already a
        single bit so the options mean nothing there.

        Limited to the number, switch and select controls - applying it to
        sensors would stop already-working entities from being created.
        """
        if self.conv_bits is None and self.conv_shift_bits is None:
            return True
        if self.control_type not in (
            ControlType.NUMBER,
            ControlType.SWITCH,
            ControlType.SELECT,
            ControlType.WATER_HEATER,
        ):
            return True

        if self.is_signed:
            _LOGGER.warning(
                "Unable to create entity for %s: %s cannot be combined with "
                "%s or %s on a writable entity",
                self.key,
                IS_SIGNED,
                CONV_BITS,
                CONV_SHIFT_BITS,
            )
            return False
        if self.conv_sum_scale:
            _LOGGER.warning(
                "Unable to create entity for %s: %s cannot be combined with "
                "%s or %s on a writable entity",
                self.key,
                CONV_SUM_SCALE,
                CONV_BITS,
                CONV_SHIFT_BITS,
            )
            return False
        return self._validate_bitfield_geometry()

    def _validate_bitfield_geometry(self) -> bool:
        """The field must be a real run of bits inside the registers it names."""
        if self.data_type == ModbusDataType.COIL:
            _LOGGER.warning(
                "Unable to create entity for %s: %s and %s have no meaning on a "
                "coil, which is already a single bit",
                self.key,
                CONV_BITS,
                CONV_SHIFT_BITS,
            )
            return False

        span: int = 16 * (self.register_count or 1)
        shift: int = self.conv_shift_bits or 0
        width: int = self.conv_bits if self.conv_bits is not None else span - shift
        if shift < 0 or width <= 0 or shift + width > span:
            _LOGGER.warning(
                "Unable to create entity for %s: %s %s / %s %s does not fit the "
                "%s bits it addresses",
                self.key,
                CONV_SHIFT_BITS,
                shift,
                CONV_BITS,
                width,
                span,
            )
            return False
        return True

    def _validate_scan_interval(self) -> bool:
        """Validate scan_interval is positive if set."""
        if self.scan_interval is not None and self.scan_interval <= 0:
            _LOGGER.warning(
                "Unable to create entity for %s: scan_interval must be > 0",
                self.key,
            )
            return False
        return True

    def _validate_string_and_float(self) -> bool:
        """Check if both string and float are defined."""
        if self.is_float and self.is_string:
            _LOGGER.warning(
                "Unable to create entity for %s: Both string and float defined",
                self.key,
            )
            return False
        return True

    def _validate_string_constraints(self) -> bool:
        """Check constraints for string entities."""
        if self.is_string and (
            self.conv_shift_bits
            or self.conv_bits
            or self.precision
            or self.conv_swap
            or self.is_signed
            or (self.conv_multiplier and int(self.conv_multiplier) != 1)
        ):
            _LOGGER.warning(
                "Unable to create entity for %s: %s, %s, %s, %s, %s, %s, %s, "
                "and %s not valid for %s",
                self.key,
                CONV_SUM_SCALE,
                CONV_SHIFT_BITS,
                CONV_BITS,
                CONV_MULTIPLIER,
                CONV_OFFSET,
                CONV_SWAP,
                IS_SIGNED,
                PRECISION,
                IS_STRING,
            )
            return False
        return True

    def _validate_float_constraints(self) -> bool:
        """Check constraints for float entities."""
        if self.is_float and (
            self.conv_shift_bits
            or self.conv_bits
            or self.is_signed
            or (self.conv_multiplier is not None and int(self.conv_multiplier) != 1)
        ):
            _LOGGER.warning(
                "Unable to create entity for %s: %s, %s, %s, and %s not valid for %s",
                self.key,
                CONV_BITS,
                CONV_SHIFT_BITS,
                IS_SIGNED,
                CONV_MULTIPLIER,
                IS_FLOAT,
            )
            return False
        return True

    def _validate_register_count(self) -> bool:
        """Check if register count is valid for float entities."""
        if self.is_float and self.register_count not in (2, 4):
            _LOGGER.warning(
                "Unable to create entity for %s: %s outside valid range not valid for %s",
                self.key,
                REGISTER_COUNT,
                IS_FLOAT,
            )
            return False

        if not self.is_string and self.register_count not in (1, 2, 4):
            _LOGGER.warning(
                "Unable to create entity for %s: %s must be 1, 2, or 4 for non-string entities",
                self.key,
                REGISTER_COUNT,
            )
            return False

        return True

    def _validate_max_change(self) -> bool:
        """Check if max_change is valid."""
        if self.max_change is not None:
            if self.is_string:
                _LOGGER.warning(
                    "Unable to create entity for %s: %s not valid for %s",
                    self.key,
                    self.max_change,
                    IS_STRING,
                )
                return False
            if self.max_change < 0:
                _LOGGER.warning(
                    "Unable to create entity for %s: %s must be ≥ 0",
                    self.key,
                    MAX_CHANGE,
                )
                return False
        return True


@dataclass(kw_only=True, frozen=True)
class ModbusSensorEntityDescription(SensorEntityDescription, ModbusEntityDescription):
    """Describes Modbus sensor register entity."""


@dataclass(kw_only=True, frozen=True)
class ModbusSwitchEntityDescription(SwitchEntityDescription, ModbusEntityDescription):
    """Describes Modbus switch holding register entity."""

    on: bool | int | None = None
    off: bool | int | None = None


@dataclass(kw_only=True, frozen=True)
class ModbusSelectEntityDescription(SelectEntityDescription, ModbusEntityDescription):
    """Describes Modbus select holding register entity."""

    select_options: dict[int, str]


@dataclass(kw_only=True, frozen=True)
class ModbusTextEntityDescription(TextEntityDescription, ModbusEntityDescription):
    """Describes Modbus text holding register entity."""


@dataclass(kw_only=True, frozen=True)
class ModbusNumberEntityDescription(NumberEntityDescription, ModbusEntityDescription):
    """Describes Modbus number holding register entity."""

    max: int
    min: int
    mode: NumberMode | None = None


@dataclass(kw_only=True, frozen=True)
class ModbusWaterHeaterEntityDescription(
    WaterHeaterEntityDescription, ModbusEntityDescription
):
    """Describes a Modbus water heater holding register entity.

    The only composite control: `register_address` is the on/off field, and the
    temperatures come from other registers of the same device. `role_keys` is
    what the YAML said - a role name against another register's key - and
    `roles` is the same map once `ModbusDeviceInfo` has resolved those keys to
    the descriptions they name.
    """

    role_keys: dict[str, str]
    roles: dict[str, ModbusEntityDescription] = field(default_factory=dict)
    operations: dict[str, int] | None = None
    on: int = 1
    off: int = 0
    away_on: int = 1
    away_off: int = 0
    temperature_precision: float | None = None
    target_temperature_step: float | None = None

    def validate(self) -> bool:
        """Validate the entity description

        Only what can be judged from this entity alone. Whether the role keys
        name registers that exist is settled later, by `ModbusDeviceInfo`,
        which is the first place the rest of the file is known.
        """
        if not super().validate():
            return False
        if not self._validate_roles():
            return False
        if not self._validate_operations():
            return False
        if self.on == self.off:
            _LOGGER.warning(
                "Unable to create entity for %s: on and off cannot be the same value",
                self.key,
            )
            return False
        return True

    def _validate_roles(self) -> bool:
        """A water heater with no tank temperature has nothing to show."""
        if WaterHeaterRole.CURRENT_TEMPERATURE not in self.role_keys:
            _LOGGER.warning(
                "Unable to create entity for %s: a water heater needs a %s role",
                self.key,
                WaterHeaterRole.CURRENT_TEMPERATURE,
            )
            return False
        return True

    def _validate_operations(self) -> bool:
        """Modes need a register to live in, and a value each."""
        if self.operations is None:
            return True
        if not isinstance(self.operations, dict) or not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in self.operations.values()
        ):
            _LOGGER.warning(
                "Unable to create entity for %s: operations must map a mode name "
                "to a whole register value",
                self.key,
            )
            return False
        if not self.operations:
            return True
        if WaterHeaterRole.OPERATION_MODE not in self.role_keys:
            _LOGGER.warning(
                "Unable to create entity for %s: operations need an %s role to "
                "read and write them",
                self.key,
                WaterHeaterRole.OPERATION_MODE,
            )
            return False
        if len(set(self.operations.values())) != len(self.operations):
            # Two modes on one value cannot both be read back, so one of them
            # would be permanently unreachable in the UI.
            _LOGGER.warning(
                "Unable to create entity for %s: operations must not share a "
                "register value",
                self.key,
            )
            return False
        return True


@dataclass(kw_only=True, frozen=True)
class ModbusBinarySensorEntityDescription(
    BinarySensorEntityDescription, ModbusEntityDescription
):
    """Describes Modbus binary sensor entity for Discrete Inputs and Registers."""

    on: bool | int | None = None
    off: bool | int | None = None
