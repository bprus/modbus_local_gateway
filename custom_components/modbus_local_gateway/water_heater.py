"""Modbus Local Gateway water heaters"""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .context import ModbusContext
from .coordinator import ModbusCoordinator, ModbusCoordinatorEntity
from .entity_management.base import (
    ModbusNumberEntityDescription,
    ModbusWaterHeaterEntityDescription,
)
from .entity_management.const import ControlType, WaterHeaterRole
from .helpers import async_setup_entities

_LOGGER: logging.Logger = logging.getLogger(__name__)

TEMPERATURE_UNITS: tuple[str, ...] = (
    UnitOfTemperature.CELSIUS,
    UnitOfTemperature.FAHRENHEIT,
    UnitOfTemperature.KELVIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Modbus Local Gateway entities."""
    await async_setup_entities(
        hass=hass,
        config_entry=config_entry,
        async_add_entities=async_add_entities,
        control=ControlType.WATER_HEATER,
        entity_class=ModbusWaterHeaterEntity,
    )


class ModbusWaterHeaterEntity(ModbusCoordinatorEntity, WaterHeaterEntity):  # type: ignore
    """Water heater entity for Modbus gateway.

    The only composite entity: its own register holds the on/off field, and the
    temperatures come from the registers its `roles` name. Each role gets its
    own coordinator context, so the shared refresh reads them whether or not
    the register also has an entity of its own.

    Availability follows the power register alone, inherited unchanged. A role
    reporting a non-value makes that one attribute unknown rather than taking
    the whole entity away: the tank temperature can be missing while the device
    is still perfectly controllable, and hiding working controls would be the
    worse answer.
    """

    def __init__(
        self,
        coordinator: ModbusCoordinator,
        ctx: ModbusContext,
        device: DeviceInfo,
    ) -> None:
        """Initialize a water heater."""
        super().__init__(coordinator, ctx=ctx, device=device)
        desc = ctx.desc
        if not isinstance(desc, ModbusWaterHeaterEntityDescription):
            raise TypeError()

        self._roles: dict[str, ModbusContext] = {
            role: ModbusContext(device_id=ctx.device_id, desc=role_desc)
            for role, role_desc in desc.roles.items()
        }
        self._operation_by_value: dict[int, str] = {
            value: name for name, value in (desc.operations or {}).items()
        }

        features = WaterHeaterEntityFeature.ON_OFF
        if WaterHeaterRole.TARGET_TEMPERATURE in self._roles:
            features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if desc.operations:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
            self._attr_operation_list = [STATE_OFF, *desc.operations]
        if WaterHeaterRole.AWAY_MODE in self._roles:
            features |= WaterHeaterEntityFeature.AWAY_MODE
        self._attr_supported_features = features

        self._attr_temperature_unit = self._tank_unit()
        self._attr_precision = (
            desc.temperature_precision
            if desc.temperature_precision is not None
            else self._tank_precision()
        )
        self._attr_target_temperature_step = (
            desc.target_temperature_step
            if desc.target_temperature_step is not None
            else self._target_number_step()
        )

    # ── configuration derived from the role descriptions ────────────────────

    def _tank_unit(self) -> str:
        """The unit the tank temperature is reported in.

        Taken from the `current_temperature` role rather than configured twice.
        Anything that is not a temperature unit is ignored, since a water
        heater has no way to express it.
        """
        desc = self.entity_description.roles.get(WaterHeaterRole.CURRENT_TEMPERATURE)
        unit = getattr(desc, "native_unit_of_measurement", None)
        if unit in TEMPERATURE_UNITS:
            return cast(str, unit)
        return UnitOfTemperature.CELSIUS

    def _tank_precision(self) -> float:
        """How finely the tank temperature can be read.

        Derived from the `current_temperature` role's multiplier: a register
        counting whole degrees cannot report tenths, and the default would
        otherwise render an integer reading as "41.0".
        """
        desc = self.entity_description.roles.get(WaterHeaterRole.CURRENT_TEMPERATURE)
        multiplier = getattr(desc, "conv_multiplier", None) or 1.0
        if multiplier >= PRECISION_WHOLE:
            return PRECISION_WHOLE
        if multiplier >= PRECISION_HALVES:
            return PRECISION_HALVES
        return PRECISION_TENTHS

    def _target_number(self) -> ModbusNumberEntityDescription | None:
        """The `target_temperature` role, when it is a number control.

        A number already declares the limits and step the device accepts, so
        they need not be configured again on the water heater.
        """
        desc = self.entity_description.roles.get(WaterHeaterRole.TARGET_TEMPERATURE)
        if isinstance(desc, ModbusNumberEntityDescription):
            return desc
        return None

    def _target_number_step(self) -> float | None:
        """The step of the `target_temperature` role, if it declares one."""
        number = self._target_number()
        return None if number is None else number.native_step

    # ── reading ─────────────────────────────────────────────────────────────

    def _role_value(self, role: str) -> float | None:
        """The last polled value of a role, as a number."""
        ctx: ModbusContext | None = self._roles.get(role)
        if ctx is None:
            return None
        value: str | int | bool | None = cast(
            ModbusCoordinator, self.coordinator
        ).get_data(ctx)
        if value is None:
            return None
        try:
            return float(value)
        except TypeError, ValueError:
            _LOGGER.debug(
                "%s: %s role read a non-numeric value %r",
                self.entity_description.key,
                role,
                value,
            )
            return None

    @property
    def entity_description(self) -> ModbusWaterHeaterEntityDescription:
        """Return the entity description."""
        return cast(ModbusWaterHeaterEntityDescription, self.coordinator_context.desc)

    @property
    def current_operation(self) -> str | None:
        """Return the current operation, ie. off, eco, performance, ...

        `None` until the power register has been read: reporting `off` for a
        register nobody has looked at yet would be a guess.
        """
        desc = self.entity_description
        power: str | int | bool | None = cast(
            ModbusCoordinator, self.coordinator
        ).get_data(self.coordinator_context)
        if power is None:
            return None
        if power != desc.on:
            return STATE_OFF
        if not desc.operations:
            return STATE_ON

        mode: float | None = self._role_value(WaterHeaterRole.OPERATION_MODE)
        if mode is None:
            return STATE_ON
        if int(mode) in self._operation_by_value:
            return self._operation_by_value[int(mode)]
        # Same choice as an unmapped `map:` value: report the raw number rather
        # than freeze on the last known mode or invent one.
        _LOGGER.debug(
            "%s: no operations entry for %s", self.entity_description.key, int(mode)
        )
        return str(int(mode))

    @property
    def current_temperature(self) -> float | None:
        """Return the current tank temperature."""
        return self._role_value(WaterHeaterRole.CURRENT_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._role_value(WaterHeaterRole.TARGET_TEMPERATURE)

    @property
    def target_temperature_high(self) -> float | None:
        """Return the highbound target temperature we try to reach."""
        return self._role_value(WaterHeaterRole.TARGET_TEMPERATURE_HIGH)

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lowbound target temperature we try to reach."""
        return self._role_value(WaterHeaterRole.TARGET_TEMPERATURE_LOW)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature.

        A limit register first, then the `target_temperature` number's own
        minimum, then the domain default.
        """
        value: float | None = self._role_value(WaterHeaterRole.MIN_TEMP)
        if value is not None:
            return value
        number = self._target_number()
        if number is not None:
            return float(number.min)
        return cast(float, super().min_temp)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature.

        A limit register first, then the `target_temperature` number's own
        maximum, then the domain default.
        """
        value: float | None = self._role_value(WaterHeaterRole.MAX_TEMP)
        if value is not None:
            return value
        number = self._target_number()
        if number is not None:
            return float(number.max)
        return cast(float, super().max_temp)

    @property
    def is_away_mode_on(self) -> bool | None:
        """Return true if away mode is on."""
        value: float | None = self._role_value(WaterHeaterRole.AWAY_MODE)
        if value is None:
            return None
        return value == self.entity_description.away_on

    # ── writing ─────────────────────────────────────────────────────────────

    def set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        raise NotImplementedError()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature.

        The service also takes an optional operation mode, which is applied
        after the temperature so the device is left in the asked-for state even
        if it was off.
        """
        temperature: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            ctx: ModbusContext | None = self._roles.get(
                WaterHeaterRole.TARGET_TEMPERATURE
            )
            if ctx is None:
                raise ValueError(
                    f"{self.entity_description.key} has no "
                    f"{WaterHeaterRole.TARGET_TEMPERATURE} role to write"
                )
            await self.write_data(float(temperature), ctx=ctx)

        operation_mode: str | None = kwargs.get(ATTR_OPERATION_MODE)
        if operation_mode is not None:
            await self.async_set_operation_mode(operation_mode)

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        raise NotImplementedError()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the water heater on."""
        await self.write_data(self.entity_description.on)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        raise NotImplementedError()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the water heater off."""
        await self.write_data(self.entity_description.off)

    def set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode."""
        raise NotImplementedError()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new target operation mode.

        A mode can only take effect while the device is on, so turning it on is
        part of selecting one.
        """
        if operation_mode == STATE_OFF:
            await self.async_turn_off()
            return

        desc = self.entity_description
        raw: int | None = (desc.operations or {}).get(operation_mode)
        if raw is None:
            raise ValueError(f"{desc.key} has no operation mode {operation_mode}")

        if (
            cast(ModbusCoordinator, self.coordinator).get_data(self.coordinator_context)
            != desc.on
        ):
            await self.write_data(desc.on)
        await self.write_data(raw, ctx=self._roles[WaterHeaterRole.OPERATION_MODE])

    def turn_away_mode_on(self) -> None:
        """Turn away mode on."""
        raise NotImplementedError()

    async def async_turn_away_mode_on(self) -> None:
        """Turn away mode on."""
        await self.write_data(
            self.entity_description.away_on,
            ctx=self._roles[WaterHeaterRole.AWAY_MODE],
        )

    def turn_away_mode_off(self) -> None:
        """Turn away mode off."""
        raise NotImplementedError()

    async def async_turn_away_mode_off(self) -> None:
        """Turn away mode off."""
        await self.write_data(
            self.entity_description.away_off,
            ctx=self._roles[WaterHeaterRole.AWAY_MODE],
        )

    # ── polling ─────────────────────────────────────────────────────────────

    def _contexts_to_read(self) -> list[ModbusContext]:
        """Every register this entity reads, not just its own."""
        return [self.coordinator_context, *self._roles.values()]

    @callback
    def _role_polled(self) -> None:
        """Nothing to do: the registration is for its context, not its callback.

        `async_add_listener` is the only way to get a register into the shared
        refresh, and the entity's own listener already writes state on every
        coordinator update - so a second write per role would be wasted work.
        """

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        for ctx in self._roles.values():
            self.async_on_remove(
                self.coordinator.async_add_listener(self._role_polled, ctx)
            )
