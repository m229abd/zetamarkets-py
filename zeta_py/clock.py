import typing
from dataclasses import dataclass

from zeta_py._layouts.clock import SYSTEM_CLOCK_LAYOUT
from zeta_py.zeta_client.accounts import AnchorpyAccount


@dataclass
class Clock(AnchorpyAccount):
    layout: typing.ClassVar = SYSTEM_CLOCK_LAYOUT
    slot: int
    epoch_start_timestamp: int
    epoch: int
    leader_schedule_epoch: int
    unix_timestamp: int

    @classmethod
    def decode(cls, data: bytes) -> "Clock":
        dec = Clock.layout.parse(data)
        return cls(
            slot=dec.slot,
            epoch_start_timestamp=dec.epoch_start_timestamp,
            epoch=dec.epoch,
            leader_schedule_epoch=dec.leader_schedule_epoch,
            unix_timestamp=dec.unix_timestamp,
        )