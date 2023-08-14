from __future__ import annotations
import typing
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from ..program_id import PROGRAM_ID


class UpdateAdminAccounts(typing.TypedDict):
    state: Pubkey
    admin: Pubkey
    new_admin: Pubkey


def update_admin(
    accounts: UpdateAdminAccounts,
    program_id: Pubkey = PROGRAM_ID,
    remaining_accounts: typing.Optional[typing.List[AccountMeta]] = None,
) -> Instruction:
    keys: list[AccountMeta] = [
        AccountMeta(pubkey=accounts["state"], is_signer=False, is_writable=True),
        AccountMeta(pubkey=accounts["admin"], is_signer=True, is_writable=False),
        AccountMeta(pubkey=accounts["new_admin"], is_signer=True, is_writable=True),
    ]
    if remaining_accounts is not None:
        keys += remaining_accounts
    identifier = b"\xa1\xb0(\xd5<\xb8\xb3\xe4"
    encoded_args = b""
    data = identifier + encoded_args
    return Instruction(program_id, data, keys)