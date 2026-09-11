"""Sensor type constants"""

from enum import StrEnum

from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfTime,
)

DEVICE = "device"

MODEL = "model"
MANUFACTURER = "manufacturer"
MAX_READ = "max_register_read"
MAX_READ_DEFAULT = 8

NAME = "name"
CONTROL_TYPE = "control"
REGISTER_ADDRESS = "address"
REGISTER_COUNT = "size"
CONV_BITS = "bits"
CONV_FLAGS = "flags"
CONV_MAP = "map"
CONV_MULTIPLIER = "multiplier"
CONV_OFFSET = "offset"
CONV_SHIFT_BITS = "shift_bits"
CONV_SUM_SCALE = "sum_scale"
CONV_SWAP = "swap"
PRECISION = "precision"
IS_FLOAT = "float"
IS_STRING = "string"
IS_SIGNED = "signed"
NEVER_RESETS = "never_resets"
MAX_CHANGE = "max_change"
CONV_UNAVAILABLE_VALUES = "unavailable_values"
UOM = "unit_of_measurement"
DEVICE_CLASS = "device_class"
STATE_CLASS = "state_class"
DEFAULT_STATE_CLASS = SensorStateClass.MEASUREMENT

UNIT = "unit"


class ModbusDataType(StrEnum):
    """Modbus data types"""

    HOLDING_REGISTER = "read_write_word"
    INPUT_REGISTER = "read_only_word"
    COIL = "read_write_boolean"
    DISCRETE_INPUT = "read_only_boolean"


class ControlType(StrEnum):
    """Valid control types"""

    SENSOR = "sensor"
    SWITCH = "switch"
    SELECT = "select"
    TEXT = "text"
    NUMBER = "number"
    BINARY_SENSOR = "binary_sensor"
    WATER_HEATER = "water_heater"


class WaterHeaterRole(StrEnum):
    """The registers a water heater composes, as named in its `water_heater` block.

    Each value is the YAML key of another register of the same device, so a
    water heater reuses those registers' scaling, bit geometry and limits
    instead of redeclaring them.
    """

    CURRENT_TEMPERATURE = "current_temperature"
    TARGET_TEMPERATURE = "target_temperature"
    TARGET_TEMPERATURE_HIGH = "target_temperature_high"
    TARGET_TEMPERATURE_LOW = "target_temperature_low"
    MIN_TEMP = "min_temp"
    MAX_TEMP = "max_temp"
    OPERATION_MODE = "operation_mode"
    AWAY_MODE = "away_mode"


# Settings, as opposed to roles, inside the `water_heater` block.
WH_OPERATIONS = "operations"
WH_ON = "on"
WH_OFF = "off"
WH_AWAY_ON = "away_on"
WH_AWAY_OFF = "away_off"
WH_TEMPERATURE_PRECISION = "temperature_precision"
WH_TARGET_TEMPERATURE_STEP = "target_temperature_step"

WATER_HEATER_SETTINGS: frozenset[str] = frozenset(
    {
        WH_OPERATIONS,
        WH_ON,
        WH_OFF,
        WH_AWAY_ON,
        WH_AWAY_OFF,
        WH_TEMPERATURE_PRECISION,
        WH_TARGET_TEMPERATURE_STEP,
    }
)
WATER_HEATER_OPTIONS: frozenset[str] = WATER_HEATER_SETTINGS | frozenset(
    role.value for role in WaterHeaterRole
)


class Units(StrEnum):
    """Valid unit types for yaml definition"""

    CELSIUS = "Celsius"
    VOLTS = "Volts"
    AMPS = "Amps"
    KWH = "kWh"
    VAR = "VAr"
    KVARH = "kVArh"
    DEGREES = "Degrees"
    HZ = "Hz"
    WATTS = "Watts"
    VA = "VoltAmps"
    SECONDS = "Seconds"
    PERCENT = "%"


class SwapType(StrEnum):
    """Modbus data types"""

    WORD = "word"
    BYTE = "byte"
    WORD_BYTE = "word_byte"


UOM_MAPPING = {
    Units.CELSIUS: {
        UNIT: UnitOfTemperature.CELSIUS,
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.VOLTS: {
        UNIT: UnitOfElectricPotential.VOLT,
        DEVICE_CLASS: SensorDeviceClass.VOLTAGE,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.AMPS: {
        UNIT: UnitOfElectricCurrent.AMPERE,
        DEVICE_CLASS: SensorDeviceClass.CURRENT,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.KWH: {
        UNIT: UnitOfEnergy.KILO_WATT_HOUR,
        DEVICE_CLASS: SensorDeviceClass.ENERGY,
        STATE_CLASS: SensorStateClass.TOTAL_INCREASING,
    },
    Units.HZ: {
        UNIT: UnitOfFrequency.HERTZ,
        DEVICE_CLASS: SensorDeviceClass.FREQUENCY,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.WATTS: {
        UNIT: UnitOfPower.WATT,
        DEVICE_CLASS: SensorDeviceClass.POWER,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.DEGREES: {
        UNIT: DEGREE,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.KVARH: {
        UNIT: "kVArh",
        STATE_CLASS: SensorStateClass.TOTAL_INCREASING,
    },
    Units.VAR: {
        UNIT: UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        DEVICE_CLASS: SensorDeviceClass.REACTIVE_POWER,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.VA: {
        UNIT: UnitOfApparentPower.VOLT_AMPERE,
        DEVICE_CLASS: SensorDeviceClass.APPARENT_POWER,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
    Units.SECONDS: {
        UNIT: UnitOfTime.SECONDS,
        DEVICE_CLASS: SensorDeviceClass.DURATION,
        STATE_CLASS: SensorStateClass.TOTAL_INCREASING,
    },
    Units.PERCENT: {
        UNIT: PERCENTAGE,
        STATE_CLASS: SensorStateClass.MEASUREMENT,
    },
}
