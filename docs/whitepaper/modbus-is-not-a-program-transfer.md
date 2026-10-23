# A function code is a byte. It is not a download.

Two modules in this repository look at Modbus, and they are forbidden to agree about what a write means.

`ModbusDissector` in `src/phos/atlas/packet/modbus.py` decodes an application data unit. `refuse_function_code` in `src/phos/atlas/program_transfer.py` raises `ValueError` for every integer it is given, including the codes the dissector knows. Download, upload, and online edit are a caller-supplied enum. No byte on the wire is a member of that enum. ADR 0302 is the record. The tests are `tests/atlas/test_program_transfer.py::test_a_function_code_is_never_a_download`.

## What the dissector actually accepts

A Modbus/TCP ADU here is a 7-byte MBAP header plus a PDU. The constants are not comments:

| Name | Value | What it bounds |
| --- | ---: | --- |
| `MODBUS_PORT` | 502 | Claim. Port alone. |
| `MBAP_HEADER_LENGTH` | 7 | Header size. |
| `_MBAP_PROTOCOL_ID` | 0 | Anything else is not this protocol. |
| `_MIN_LENGTH_FIELD` | 2 | Unit id and one function code. |
| `_MAX_LENGTH_FIELD` | 254 | Unit id plus a 253-byte PDU. |
| `MAX_READ_COILS` | 2000 | Coils or discrete inputs per read. |
| `MAX_READ_REGISTERS` | 125 | Registers per read. |
| `MAX_WRITE_COILS` | 1968 | Coils per write-multiple. |
| `MAX_WRITE_REGISTERS` | 123 | Registers per write-multiple. |

`_MAX_LENGTH_FIELD` is checked before the payload is used to size anything. The MBAP cap is not enough on its own. A 253-byte PDU can carry a byte count of 251, which would unpack to 2,008 coils, eight past a legal read. `_MAX_READ_RESPONSE_BYTES` is the second cap, on the count field inside the ADU. ADR 0012 is why the length is checked before the read.

`claims` returns true from the port alone. Garbage aimed at 502 is still this dissector's problem. Falling through to "no dissector covers this" would be the wrong sentence about rubbish aimed at a PLC. The failure mode is a `MalformedFrame` with a specific `MalformedReason`. The decode does not throw. There is no `try` wrapped around it to make that true. The checks come first. `tests/atlas/packet/test_hardening.py` throws mutated frames at it and asserts nothing escapes.

Two capabilities are absent and the absence is a refusal, not a silent guess. There is no TCP reassembly, so an ADU split across segments, or two ADUs in one buffer, comes back as `LENGTH_MISMATCH` or `TRAILING_BYTES`. Dissection is stateless. A response is not matched to a request this module never saw. Fields the response does not carry stay `None`. They are not back-filled.

`FunctionCode` is a namespace of integers, not an `Enum`. An unrecognised code is still a valid message: `_function_name` returns `unknown(<n>)`. An enum would invite converting the wire value into a closed set and dropping the rest. The codes that are named are the eight everybody already knows:

```python
READ_COILS = 1
READ_DISCRETE_INPUTS = 2
READ_HOLDING_REGISTERS = 3
READ_INPUT_REGISTERS = 4
WRITE_SINGLE_COIL = 5
WRITE_SINGLE_REGISTER = 6
WRITE_MULTIPLE_COILS = 15
WRITE_MULTIPLE_REGISTERS = 16
```

Exception responses are function code with bit 7 set (`_EXCEPTION_MASK = 0x80`). That is a server complaining. It is not an attack label.

## What a decoded write is allowed to become

`is_write` and `is_register_write` in `src/phos/atlas/packet/commands.py` classify activity. Coil writes are kept as activity and thrown out of value ranges. Function 5 carries `0x0000` or `0xFF00`. Function 15 carries bits unpacked to `0` or `1`. Both mean on or off, three orders of magnitude apart. A range computed over that pair describes neither encoding. The per-function counts and the write-address features still see the coil. The meaningless number does not enter the feature.

`featurise_commands` turns a device's messages over a window into ordinary observations: volume, function mix, write targets, read/write balance, polling rhythm. `learn_device_command_graph` and `compare_to_graph` add the structure between devices. The comparison emits exactly three finding names:

- `unknown_command_relationship` — a pair that was not in the learned graph.
- `unexpected_command_function` — a known pair, a function code the learned edge did not carry.
- `silent_command_relationship` — a learned pair that went quiet over the horizon.

Those are observations. They are not verdicts. ADR 0014: an unexpected function on a known link supports `engineering_maintenance` and `unauthorised_control_activity` equally. A commissioning engineer and an intruder leave the same new function on a station the plant already trusts. A marked unknown master is narrower. A device that never commanded this target begins to write. That finding supports the attack explanation and contradicts maintenance. The two issuer kinds are scored apart. Known-station unique lead is 0 of 16. Unknown-master unique lead is 1 of 4, on attacks this repository wrote, with the caveat that an attribution rank is not a rate. They are not pooled. "≥70%" is not a pass mark on these files (ADR 0038, ADR 0049).

## The function that refuses the promotion

`refuse_function_code` does not inspect the integer. The body is a raise:

```python
raise ValueError(
    f"function code {code} is not a program transfer; "
    "download, upload, and online_edit are supplied by the caller"
)
```

Codes 1, 2, 3, 4, 5, 6, 15 and 16 are the ones ADR 0302 names. The function raises for any other integer as well. `ProgramAct` has three members: `download`, `upload`, `online_edit`. `transfer_report` takes one of those, plus bookings and work orders the caller already holds. An empty list stays empty. A work order with `act is None` and only a tag does not cover. Cover is interval containment, inclusive, of the same act. Withdrawal clears `alert`, `instruction`, and `next_observation`. `lead` stays `None`. `tied_lead_ids` stays the two story ids. A missing booking prints `Go and look.` It does not print "attack".

The equal confidence used to force that tie is `_TIED_CONFIDENCE = 0.5`. It is an argument to `Hypothesis`. It is not an attribute of `TransferReport`. Putting it on a screen would be a fabricated probability. Hypothesis confidence in this repository is uncalibrated and must not be shown (Constitution §3.3, `UNCALIBRATED_HYPOTHESIS_CONFIDENCE_CAVEAT` in `src/phos/atlas/engine.py`).

## The measurement that is missing

`discover_labelled_command_corpora` is empty. `scripts/evaluate_command_detection.py` is written to refuse a metric when the corpus is absent, and to name what the corpus would have to contain. S7 process parquet is not a pcap. 3W labels are faults. There is no public capture in which a credentialed write and an attacker's identical write are both labelled. Until that file exists, the parser can be proved on fixtures and the graph can be proved on fixtures. Neither number is a detection rate. `UNMEASURED_COMMAND_DETECTION_CAVEAT` is the sentence that has to travel with any output of that path.
