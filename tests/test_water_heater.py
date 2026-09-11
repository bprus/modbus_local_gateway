"""Water heater tests"""

# pylint: disable=unexpected-keyword-arg, protected-access
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.water_heater import WaterHeaterEntityFeature
from homeassistant.const import (
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.modbus_local_gateway.const import CONF_DEVICE_ID, DOMAIN
from custom_components.modbus_local_gateway.context import ModbusContext
from custom_components.modbus_local_gateway.coordinator import ModbusCoordinator
from custom_components.modbus_local_gateway.entity_management.base import (
    ModbusNumberEntityDescription,
    ModbusSensorEntityDescription,
    ModbusWaterHeaterEntityDescription,
)
from custom_components.modbus_local_gateway.entity_management.const import (
    ControlType,
    ModbusDataType,
    WaterHeaterRole,
)
from custom_components.modbus_local_gateway.entity_management.modbus_device_info import (
    ModbusDeviceInfo,
)
from custom_components.modbus_local_gateway.water_heater import (
    ModbusWaterHeaterEntity,
    async_setup_entry,
)

TANK = ModbusSensorEntityDescription(
    key="tank_temperature",
    register_address=115,
    data_type=ModbusDataType.HOLDING_REGISTER,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
)
SETPOINT = ModbusNumberEntityDescription(
    key="dhw_setpoint",
    register_address=4,
    data_type=ModbusDataType.HOLDING_REGISTER,
    control_type=ControlType.NUMBER,
    min=20,
    max=60,
    native_step=1,
)
LOWER = ModbusSensorEntityDescription(
    key="dhw_lower_limit",
    register_address=208,
    data_type=ModbusDataType.HOLDING_REGISTER,
)
UPPER = ModbusSensorEntityDescription(
    key="dhw_upper_limit",
    register_address=207,
    data_type=ModbusDataType.HOLDING_REGISTER,
)
BOOST = ModbusSensorEntityDescription(
    key="fast_dhw_raw",
    register_address=7,
    data_type=ModbusDataType.HOLDING_REGISTER,
)
AWAY = ModbusSensorEntityDescription(
    key="holiday_mode",
    register_address=5,
    data_type=ModbusDataType.HOLDING_REGISTER,
    conv_bits=1,
    conv_shift_bits=3,
)


def make_description(**overrides) -> ModbusWaterHeaterEntityDescription:
    """A resolved water heater description, as ModbusDeviceInfo would hand it over."""
    params = {
        "key": "dhw_tank",
        "register_address": 0,
        "conv_bits": 1,
        "conv_shift_bits": 2,
        "data_type": ModbusDataType.HOLDING_REGISTER,
        "control_type": ControlType.WATER_HEATER,
        "role_keys": {
            WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK.key,
            WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT.key,
        },
        "roles": {
            WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
            WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT,
        },
    }
    params.update(overrides)
    return ModbusWaterHeaterEntityDescription(**params)


def make_entity(
    desc: ModbusWaterHeaterEntityDescription, store: dict[str, object]
) -> tuple[ModbusWaterHeaterEntity, MagicMock]:
    """A water heater wired to a coordinator whose data is `store`."""
    coordinator = MagicMock(spec=ModbusCoordinator)
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {"host": "modbus.home"}
    coordinator.client = AsyncMock()
    coordinator.get_data = MagicMock(side_effect=lambda ctx: store.get(ctx.desc.key))

    entity = ModbusWaterHeaterEntity(
        coordinator=coordinator,
        ctx=ModbusContext(device_id=1, desc=desc),
        device=MagicMock(),
    )
    entity._handle_coordinator_update = MagicMock()
    return entity, coordinator


def written(coordinator: MagicMock) -> list[tuple[str, object]]:
    """The (register key, value) pairs written since the last call."""
    calls = [
        (call.args[0].desc.key, call.args[1])
        for call in coordinator.client.write_data.call_args_list
    ]
    coordinator.client.write_data.reset_mock()
    return calls


@pytest.mark.asyncio
async def test_setup_entry(hass) -> None:
    """Test the HA setup function"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "127.0.0.1",
            "port": "1234",
            CONF_DEVICE_ID: 1,
            "filename": "test.yaml",
        },
    )
    callback = MagicMock()
    coordinator = AsyncMock()
    gw_dev = MagicMock()
    type(coordinator).gateway_device = PropertyMock(return_value=gw_dev)
    identifiers = PropertyMock()
    identifiers.return_value = ["a"]
    type(gw_dev).identifiers = identifiers
    hass.data[DOMAIN] = {"127.0.0.1:1234:1": coordinator}

    pm1 = PropertyMock(return_value=[make_description(), TANK, SETPOINT])
    pm2 = PropertyMock(return_value="")

    with (
        patch(
            "custom_components.modbus_local_gateway.entity_management.modbus_device_info.load_yaml",
            return_value={"device": MagicMock()},
        ),
        patch.object(ModbusDeviceInfo, "entity_descriptions", pm1),
        patch.object(ModbusDeviceInfo, "manufacturer", pm2),
        patch.object(ModbusDeviceInfo, "model", pm2),
    ):
        await async_setup_entry(hass, entry, callback.add)

        callback.add.assert_called_once()
        # only the water heater, not the registers it composes
        assert len(callback.add.call_args[0][0]) == 1
        assert callback.add.call_args[1] == {"update_before_add": False}


def test_features_follow_the_configured_roles() -> None:
    """Each optional role and setting turns on exactly one feature."""
    entity, _ = make_entity(make_description(), {})
    assert entity.supported_features == (
        WaterHeaterEntityFeature.ON_OFF | WaterHeaterEntityFeature.TARGET_TEMPERATURE
    )
    assert entity.operation_list is None

    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
        WaterHeaterRole.AWAY_MODE.value: AWAY,
    }
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()},
            roles=roles,
            operations={"eco": 0, "performance": 1},
        ),
        {},
    )
    assert entity.supported_features == (
        WaterHeaterEntityFeature.ON_OFF
        | WaterHeaterEntityFeature.OPERATION_MODE
        | WaterHeaterEntityFeature.AWAY_MODE
    )
    # off is always selectable: it is the power register, not an operation
    assert entity.operation_list == [STATE_OFF, "eco", "performance"]


def test_temperatures_come_from_the_roles() -> None:
    """Every temperature is read from the register its role names."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT,
        WaterHeaterRole.MIN_TEMP.value: LOWER,
        WaterHeaterRole.MAX_TEMP.value: UPPER,
    }
    store = {
        "dhw_tank": 1,
        TANK.key: 41,
        SETPOINT.key: 37,
        LOWER.key: 20,
        UPPER.key: 60,
    }
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()}, roles=roles
        ),
        store,
    )

    assert entity.current_temperature == 41
    assert entity.target_temperature == 37
    assert entity.min_temp == 20
    assert entity.max_temp == 60
    assert entity.temperature_unit == UnitOfTemperature.CELSIUS


def test_limits_fall_back_to_the_target_number() -> None:
    """With no limit registers, the target number's own min and max are used.

    They are the same limits the device accepts, already declared once.
    """
    entity, _ = make_entity(make_description(), {})
    assert entity.min_temp == SETPOINT.min
    assert entity.max_temp == SETPOINT.max
    assert entity.target_temperature_step == SETPOINT.native_step


def test_limit_registers_beat_the_target_number() -> None:
    """A live limit register is preferred over the number's static declaration."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT,
        WaterHeaterRole.MIN_TEMP.value: LOWER,
        WaterHeaterRole.MAX_TEMP.value: UPPER,
    }
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()}, roles=roles
        ),
        {LOWER.key: 35, UPPER.key: 55},
    )
    assert entity.min_temp == 35
    assert entity.max_temp == 55


def test_target_temperature_range_is_reported() -> None:
    """A device with a target range can report it, read-only.

    `water_heater.set_temperature` does not accept the high and low fields, so
    there is nothing to write - but the attributes are always published.
    """
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.TARGET_TEMPERATURE_HIGH.value: UPPER,
        WaterHeaterRole.TARGET_TEMPERATURE_LOW.value: LOWER,
    }
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()}, roles=roles
        ),
        {UPPER.key: 55, LOWER.key: 45},
    )
    assert entity.target_temperature_high == 55
    assert entity.target_temperature_low == 45
    assert entity.target_temperature is None


def test_limits_fall_back_to_the_domain_default() -> None:
    """With neither limit registers nor a target number, Home Assistant decides.

    Pins the MRO: `min_temp` and `max_temp` defer to WaterHeaterEntity, which
    sits behind ModbusCoordinatorEntity in the bases.
    """
    roles = {WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK}
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()}, roles=roles
        ),
        {},
    )
    # the domain default is 110-140 degrees Fahrenheit
    assert round(entity.min_temp, 2) == 43.33
    assert round(entity.max_temp, 2) == 60.0
    assert entity.target_temperature_step is None


def test_precision_follows_the_tank_multiplier() -> None:
    """A register counting whole degrees must not report tenths."""
    for multiplier, expected in (
        (None, PRECISION_WHOLE),
        (1.0, PRECISION_WHOLE),
        (0.5, PRECISION_HALVES),
        (0.1, PRECISION_TENTHS),
    ):
        tank = ModbusSensorEntityDescription(
            key=TANK.key,
            register_address=115,
            data_type=ModbusDataType.HOLDING_REGISTER,
            conv_multiplier=multiplier,
        )
        roles = {WaterHeaterRole.CURRENT_TEMPERATURE.value: tank}
        entity, _ = make_entity(
            make_description(
                role_keys={r: d.key for r, d in roles.items()}, roles=roles
            ),
            {},
        )
        assert entity.precision == expected, multiplier

    # an explicit setting wins over the derived one
    entity, _ = make_entity(
        make_description(temperature_precision=PRECISION_TENTHS), {}
    )
    assert entity.precision == PRECISION_TENTHS


def test_operation_reports_off_on_and_the_mode() -> None:
    """The power register decides off; the operation register decides which mode."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    store: dict[str, object] = {}
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()},
            roles=roles,
            operations={"eco": 0, "performance": 1},
        ),
        store,
    )

    # nothing read yet: unknown, not a guess of off
    assert entity.current_operation is None

    store["dhw_tank"] = 0
    assert entity.current_operation == STATE_OFF

    store["dhw_tank"] = 1
    store[BOOST.key] = 0
    assert entity.current_operation == "eco"
    store[BOOST.key] = 1
    assert entity.current_operation == "performance"

    # an unconfigured value reports the raw number rather than freezing on the
    # last known mode - the same choice the sensor platform makes for `map:`
    store[BOOST.key] = 9
    assert entity.current_operation == "9"

    # on, but the mode register has not been read
    del store[BOOST.key]
    assert entity.current_operation == STATE_ON


def test_operation_is_on_without_configured_modes() -> None:
    """With no operations, the entity is a plain on/off water heater."""
    entity, _ = make_entity(make_description(), {"dhw_tank": 1})
    assert entity.current_operation == STATE_ON
    assert entity.supported_features & WaterHeaterEntityFeature.OPERATION_MODE == 0


def test_custom_on_off_values() -> None:
    """A power field is not always 1 and 0."""
    entity, _ = make_entity(make_description(on=2, off=3), {"dhw_tank": 2})
    assert entity.current_operation == STATE_ON
    entity, _ = make_entity(make_description(on=2, off=3), {"dhw_tank": 3})
    assert entity.current_operation == STATE_OFF


def test_non_numeric_role_is_not_a_temperature(caplog) -> None:
    """A role naming a mapped register reads a label, which is not a temperature."""
    entity, _ = make_entity(make_description(), {TANK.key: "Heat"})
    with caplog.at_level("DEBUG"):
        assert entity.current_temperature is None
    assert "non-numeric" in caplog.text


@pytest.mark.asyncio
async def test_set_temperature_writes_the_target_role() -> None:
    """The temperature goes to the target register, not the entity's own."""
    entity, coordinator = make_entity(make_description(), {"dhw_tank": 1})
    await entity.async_set_temperature(temperature=48)
    assert written(coordinator) == [(SETPOINT.key, 48.0)]

    # and the register just written is the one re-read
    coordinator.async_update_entities.assert_awaited_once()
    assert [
        ctx.desc.key for ctx in coordinator.async_update_entities.call_args[0][0]
    ] == [SETPOINT.key]


@pytest.mark.asyncio
async def test_set_temperature_without_a_target_role() -> None:
    """Asking to set a temperature the device has no register for must not be silent."""
    roles = {WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK}
    entity, coordinator = make_entity(
        make_description(role_keys={r: d.key for r, d in roles.items()}, roles=roles),
        {},
    )
    with pytest.raises(ValueError):
        await entity.async_set_temperature(temperature=48)
    assert written(coordinator) == []


@pytest.mark.asyncio
async def test_set_temperature_also_applies_an_operation_mode() -> None:
    """`water_heater.set_temperature` takes an optional mode; honour it."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    entity, coordinator = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()},
            roles=roles,
            operations={"eco": 0, "performance": 1},
        ),
        {"dhw_tank": 1},
    )
    await entity.async_set_temperature(temperature=50, operation_mode="performance")
    assert written(coordinator) == [(SETPOINT.key, 50.0), (BOOST.key, 1)]


@pytest.mark.asyncio
async def test_set_temperature_with_no_temperature_writes_nothing() -> None:
    """The service takes an optional mode, so a call may carry no temperature."""
    entity, coordinator = make_entity(make_description(), {"dhw_tank": 1})
    await entity.async_set_temperature()
    assert written(coordinator) == []


@pytest.mark.asyncio
async def test_turn_on_and_off_write_the_power_field() -> None:
    """On and off are the entity's own register, through the bit field write path."""
    entity, coordinator = make_entity(make_description(), {"dhw_tank": 0})
    await entity.async_turn_on()
    await entity.async_turn_off()
    assert written(coordinator) == [("dhw_tank", 1), ("dhw_tank", 0)]


@pytest.mark.asyncio
async def test_setting_a_mode_powers_on_first() -> None:
    """A mode cannot take effect while the device is off."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    store: dict[str, object] = {"dhw_tank": 0}
    entity, coordinator = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()},
            roles=roles,
            operations={"eco": 0, "performance": 1},
        ),
        store,
    )

    await entity.async_set_operation_mode("performance")
    assert written(coordinator) == [("dhw_tank", 1), (BOOST.key, 1)]

    # already on: only the mode is written
    store["dhw_tank"] = 1
    await entity.async_set_operation_mode("eco")
    assert written(coordinator) == [(BOOST.key, 0)]

    # off is the power register, not an operation value
    await entity.async_set_operation_mode(STATE_OFF)
    assert written(coordinator) == [("dhw_tank", 0)]


@pytest.mark.asyncio
async def test_unknown_operation_mode_raises() -> None:
    """A mode the config does not define must not write anything."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    entity, coordinator = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()},
            roles=roles,
            operations={"eco": 0},
        ),
        {"dhw_tank": 1},
    )
    with pytest.raises(ValueError):
        await entity.async_set_operation_mode("performance")
    assert written(coordinator) == []


@pytest.mark.asyncio
async def test_away_mode() -> None:
    """Away mode reads and writes its own register, with configurable values."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.AWAY_MODE.value: AWAY,
    }
    store: dict[str, object] = {}
    desc = make_description(
        role_keys={role: d.key for role, d in roles.items()},
        roles=roles,
        away_on=1,
        away_off=0,
    )
    entity, coordinator = make_entity(desc, store)

    assert entity.is_away_mode_on is None
    store[AWAY.key] = 0
    assert entity.is_away_mode_on is False
    store[AWAY.key] = 1
    assert entity.is_away_mode_on is True

    await entity.async_turn_away_mode_on()
    await entity.async_turn_away_mode_off()
    assert written(coordinator) == [(AWAY.key, 1), (AWAY.key, 0)]


def test_contexts_to_read_covers_every_role() -> None:
    """The entity's own refresh must read the registers it composes, not just its own."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.TARGET_TEMPERATURE.value: SETPOINT,
        WaterHeaterRole.MAX_TEMP.value: UPPER,
    }
    entity, _ = make_entity(
        make_description(
            role_keys={role: desc.key for role, desc in roles.items()}, roles=roles
        ),
        {},
    )
    assert [ctx.desc.key for ctx in entity._contexts_to_read()] == [
        "dhw_tank",
        TANK.key,
        SETPOINT.key,
        UPPER.key,
    ]


@pytest.mark.asyncio
async def test_roles_are_registered_with_the_coordinator() -> None:
    """Each role needs a listener, which is how its register joins the shared refresh."""
    entity, coordinator = make_entity(make_description(), {})
    entity.async_on_remove = MagicMock()

    with patch(
        "custom_components.modbus_local_gateway.coordinator.ModbusCoordinatorEntity"
        ".async_added_to_hass",
        AsyncMock(),
    ):
        await entity.async_added_to_hass()

    registered = [
        call.args[1].desc.key for call in coordinator.async_add_listener.call_args_list
    ]
    assert registered == [TANK.key, SETPOINT.key]
    # the callback is a placeholder: the entity's own listener writes the state
    assert entity._role_polled() is None


def test_description_requires_a_tank_temperature(caplog) -> None:
    """A water heater with no current temperature has nothing to show."""
    desc = ModbusWaterHeaterEntityDescription(
        key="dhw_tank",
        register_address=0,
        data_type=ModbusDataType.HOLDING_REGISTER,
        control_type=ControlType.WATER_HEATER,
        role_keys={},
    )
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "current_temperature" in caplog.text


def test_description_rejects_modes_without_a_register(caplog) -> None:
    """Operations need a register to read them from and write them to."""
    desc = make_description(operations={"eco": 0, "performance": 1})
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "operation_mode" in caplog.text


def test_description_rejects_modes_sharing_a_value(caplog) -> None:
    """Two modes on one value would leave one of them unreachable."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    desc = make_description(
        role_keys={role: d.key for role, d in roles.items()},
        roles=roles,
        operations={"eco": 1, "performance": 1},
    )
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "share a register value" in caplog.text


def test_description_rejects_non_integer_modes(caplog) -> None:
    """An operation maps to a register value, which is a whole number."""
    roles = {
        WaterHeaterRole.CURRENT_TEMPERATURE.value: TANK,
        WaterHeaterRole.OPERATION_MODE.value: BOOST,
    }
    desc = make_description(
        role_keys={role: d.key for role, d in roles.items()},
        roles=roles,
        operations={"eco": "cheap"},
    )
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "whole register value" in caplog.text


def test_description_rejects_identical_on_and_off(caplog) -> None:
    """A power field that writes the same value either way controls nothing."""
    desc = make_description(on=1, off=1)
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "cannot be the same value" in caplog.text


def test_description_validates_the_power_bit_field(caplog) -> None:
    """The power field's geometry is checked, as it is for every writable bit field."""
    desc = make_description(conv_bits=4, conv_shift_bits=14)
    with caplog.at_level("WARNING"):
        assert desc.validate() is False
    assert "does not fit" in caplog.text


def test_wrong_description_type_is_rejected() -> None:
    """The platform only builds entities from a water heater description."""
    coordinator = MagicMock(spec=ModbusCoordinator)
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.data = {"host": "modbus.home"}
    with pytest.raises(TypeError):
        ModbusWaterHeaterEntity(
            coordinator=coordinator,
            ctx=ModbusContext(device_id=1, desc=TANK),
            device=MagicMock(),
        )
