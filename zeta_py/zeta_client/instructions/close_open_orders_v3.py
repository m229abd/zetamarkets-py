from __future__ import annotations
import typing
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
import borsh_construct as borsh
from .. import types
from ..program_id import PROGRAM_ID


class CloseOpenOrdersV3Args(typing.TypedDict):
    map_nonce: int
    asset: types.asset.AssetKind


layout = borsh.CStruct("map_nonce" / borsh.U8, "asset" / types.asset.layout)


class CloseOpenOrdersV3Accounts(typing.TypedDict):
    state: Pubkey
    pricing: Pubkey
    dex_program: Pubkey
    open_orders: Pubkey
    cross_margin_account: Pubkey
    authority: Pubkey
    market: Pubkey
    serum_authority: Pubkey
    open_orders_map: Pubkey


def close_open_orders_v3(
    args: CloseOpenOrdersV3Args,
    accounts: CloseOpenOrdersV3Accounts,
    program_id: Pubkey = PROGRAM_ID,
    remaining_accounts: typing.Optional[typing.List[AccountMeta]] = None,
) -> Instruction:
    keys: list[AccountMeta] = [
        AccountMeta(pubkey=accounts["state"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["pricing"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["dex_program"], is_signer=False, is_writable=False),
        AccountMeta(pubkey=accounts["open_orders"], is_signer=False, is_writable=True),
        AccountMeta(
            pubkey=accounts["cross_margin_account"], is_signer=False, is_writable=True
        ),
        AccountMeta(pubkey=accounts["authority"], is_signer=True, is_writable=True),
        AccountMeta(pubkey=accounts["market"], is_signer=False, is_writable=False),
        AccountMeta(
            pubkey=accounts["serum_authority"], is_signer=False, is_writable=False
        ),
        AccountMeta(
            pubkey=accounts["open_orders_map"], is_signer=False, is_writable=True
        ),
    ]
    if remaining_accounts is not None:
        keys += remaining_accounts
    identifier = b"\xcf\x0f\xc6J\xc5\xe4\xb0\x1e"
    encoded_args = layout.build(
        {
            "map_nonce": args["map_nonce"],
            "asset": args["asset"].to_encodable(),
        }
    )
    data = identifier + encoded_args
    return Instruction(program_id, data, keys)
