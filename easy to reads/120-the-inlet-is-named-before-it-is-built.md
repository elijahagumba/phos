# 120. The inlet is named before it is built

*Named rows go in. A function code stays a function code. ADR 0325.*

The operator page already knows what a broken law is. It does not yet have a
front door for a historian row or a Modbus message that has already been
taken apart. This record names that door. It does not build it, and it does
not open a capture or a historian file.

A row becomes a setpoint step only when the caller listed that tag as a
setpoint. A station is a name the caller wrote down. A program transfer is
one of the three acts the caller named. A function code is none of those.
A frame that failed to parse stays a failed frame. It does not become a
slot.

The ten controller fields are the ones the page already uses. The caller
either supplies all of them at one time, or supplies none. The function
does not guess the missing ones.

Nothing was scored. Version 1 stays at eight of twelve. The old detector
files were not edited. This page is not a result about a plant.
