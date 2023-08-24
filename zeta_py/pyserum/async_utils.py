import typing
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from spl.token.constants import WRAPPED_SOL_MINT

from zeta_py.pyserum._layouts.market import MINT_LAYOUT


async def load_bytes_data(addr: Pubkey, conn: AsyncClient) -> typing.Optional[bytes]:
    res = await conn.get_account_info(addr)
    if not hasattr(res, "value"):
        raise Exception("Cannot load byte data.")
    return res.value.data if res.value is not None else None


async def load_multiple_bytes_data(addrs: list[Pubkey], conn: AsyncClient) -> list[typing.Optional[bytes]]:
    res = await conn.get_multiple_accounts(addrs)
    if not hasattr(res, "value"):
        raise Exception("Cannot load byte data.")
    return [v.data if v is not None else None for v in res.value]


async def get_mint_decimals(conn: AsyncClient, mint_pub_key: Pubkey) -> int:
    """Get the mint decimals for a token mint"""
    if mint_pub_key == WRAPPED_SOL_MINT:
        return 9

    bytes_data = await load_bytes_data(mint_pub_key, conn)
    if bytes_data is None:
        return None
    return parse_mint_decimals(bytes_data)


def parse_mint_decimals(bytes_data: bytes) -> int:
    return MINT_LAYOUT.parse(bytes_data).decimals
