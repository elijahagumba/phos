# 98. Eight on the page

*An unbooked program change keeps its place among the eight. ADR 0303.*

A shift shows eight alerts. An unbooked download, upload, or online edit is one of
them, and the instruction is still go and look. Both stories stay, and neither is
chosen. A transfer that a booking already covers does not take a place.

If the page is full, the alert that leaves is the other one with the lowest score.
The unbooked transfer stays. If nine unbooked transfers arrive in one shift, eight
stay, the earliest first. A register write is still not a download. An empty booking
list is still empty.

The old alert counter is unchanged. Nothing was measured on a plant. Version 1 still
stands at eight of twelve.
