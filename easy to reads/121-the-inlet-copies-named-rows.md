# 121. The inlet copies named rows

*The door named in the last note is now a function. Nothing was scored. ADR 0325.*

`inlet_from_tables` takes rows the caller already named and returns the
arguments the operator page already accepts. A tag becomes a setpoint step
only when the caller listed it. A Modbus message becomes a write only beside
a station name the caller wrote down. The function does not read the
function code, the unit id, or either address. An integer offered as a
program act is refused, and no inlet comes back. A frame that failed to
parse is refused the same way.

The tests build those rows themselves. They do not open a capture. An empty
register still evaluates nothing. Nine outside writes still keep the
earliest eight. A sentence on that page still names its law.

Version 1 stays at eight of twelve. The old detector files were not edited.
This is not a result about a plant.
