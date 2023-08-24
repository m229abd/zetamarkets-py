import logging
from dataclasses import dataclass

from anchorpy import Provider, Wallet
from solana.blockhash import BlockhashCache
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.transaction import Transaction
from solders.pubkey import Pubkey

from zeta_py import constants, pda, utils
from zeta_py.accounts import Account
from zeta_py.exchange import Exchange
from zeta_py.pyserum.enums import Side
from zeta_py.pyserum.market.types import Order
from zeta_py.types import Asset, Network, OrderOptions, OrderType, Position
from zeta_py.zeta_client.accounts.cross_margin_account import CrossMarginAccount
from zeta_py.zeta_client.accounts.cross_margin_account_manager import (
    CrossMarginAccountManager,
)
from zeta_py.zeta_client.instructions import (
    deposit_v2,
    initialize_cross_margin_account,
    initialize_cross_margin_account_manager,
    initialize_open_orders_v3,
    place_perp_order_v3,
)
from solders.system_program import ID as SYS_PROGRAM_ID
from solders.sysvar import RENT
from spl.token.constants import ASSOCIATED_TOKEN_PROGRAM_ID, TOKEN_PROGRAM_ID

@dataclass
class Client:
    """
    Cross margin client
    """

    provider: Provider
    network: Network
    connection: AsyncClient
    exchange: Exchange
    margin_account: Account[CrossMarginAccount]
    balance: int
    positions: dict[Asset, Position]
    open_orders: list[Asset, list[Order]]

    # _margin_account_manager: Account[CrossMarginAccountManager]
    _open_orders_addresses: dict[Asset, Pubkey]
    _margin_account_manager_address: Pubkey
    _combined_vault_address: Pubkey
    _combined_socialized_loss_address: Pubkey
    _user_usdc_address: Pubkey
    _logger: logging.Logger
    _blockhash_cache = BlockhashCache()

    @classmethod
    async def load(
        cls,
        network: Network,
        connection: AsyncClient,
        wallet: Wallet,
        assets: list[Asset] = Asset.all(),
        tx_opts: TxOpts = constants.DEFAULT_TX_OPTS,
        subscribe: bool = False,
    ):
        """
        Create a new client
        """
        provider = Provider(
            connection,
            wallet,
            tx_opts,
        )
        exchange = await Exchange.load(
            network=network,
            connection=connection,
            assets=assets,
            tx_opts=tx_opts,
            subscribe=subscribe,
        )
        # TODO: ideally batch these fetches
        margin_account_address = pda.get_margin_account_address(exchange.program_id, wallet.public_key, 0)
        margin_account = await Account[CrossMarginAccount].load(margin_account_address, connection, CrossMarginAccount)

        balance = utils.convert_fixed_int_to_decimal(margin_account.account.balance)

        positions = {}
        open_orders = {}
        _open_orders_addresses = {}
        for asset in assets:
            # positions per market
            positions[asset] = Position(
                utils.convert_fixed_lot_to_decimal(
                    margin_account.account.product_ledgers[asset.to_index()].position.size
                ),
                utils.convert_fixed_int_to_decimal(
                    margin_account.account.product_ledgers[asset.to_index()].position.cost_of_trades
                ),
            )

            # open orders per market
            open_orders_address = pda.get_open_orders_address(
                exchange.program_id,
                constants.DEX_PID[network],
                exchange.markets[asset].address,
                margin_account.address,
            )
            _open_orders_addresses[asset] = open_orders_address
            open_orders[asset] = await exchange.markets[asset]._serum_market.load_orders_for_owner(open_orders_address)

        # additional addresses to cache
        _margin_account_manager_address = pda.get_cross_margin_account_manager_address(
            exchange.program_id, provider.wallet.public_key
        )
        _combined_vault_address = pda.get_combined_vault_address(exchange.program_id)
        _combined_socialized_loss_address = pda.get_combined_socialized_loss_address(exchange.program_id)
        _user_usdc_address = pda.get_associated_token_address(provider.wallet.public_key, constants.USDC_MINT[network])

        logger = logging.getLogger(f"{__name__}.{cls.__name__}")

        return cls(
            provider,
            network,
            connection,
            exchange,
            margin_account,
            balance,
            positions,
            open_orders,
            _open_orders_addresses,
            _margin_account_manager_address,
            _combined_vault_address,
            _combined_socialized_loss_address,
            _user_usdc_address,
            logger,
        )

    async def _check_user_usdc_account_exists(self):
        if not hasattr(self, "_user_usdc_account"):
            # If they don't have USDC wallet this will be null
            resp = await self.connection.get_account_info_json_parsed(self._user_usdc_address)
            self._user_usdc_account = resp.value
        return self._user_usdc_account is not None

    async def _check_margin_account_manager_exists(self):
        if not hasattr(self, "_margin_account_manager"):
            # If they don't have margin account manager this will be null
            self._margin_account_manager = await Account[CrossMarginAccountManager].load(
                self._margin_account_manager_address, self.connection, CrossMarginAccountManager
            )  # None if no manager exists
        return self._margin_account_manager._is_initialized

    # async def _check_open_orders_account_exists(self, asset: Asset):
    #     if not hasattr(self.open_orders[asset], "_margin_account_manager"):
    #         # If they don't have margin account manager this will be null
    #         self._margin_account_manager = await Account[CrossMarginAccountManager].load(
    #             self._margin_account_manager_address, self.connection, CrossMarginAccountManager
    #         )  # None if no manager exists
    #     return self._margin_account_manager._is_initialized

    # TODO: deposit
    async def deposit(self, amount: float, subaccount_index: int = 0):
        tx = Transaction()
        if not await self._check_margin_account_manager_exists():
            self._logger.info("User has no cross-margin account manager, creating one...")
            tx.add(
                initialize_cross_margin_account_manager(
                    {
                        "cross_margin_account_manager": self._margin_account_manager_address,
                        "authority": self.provider.wallet.public_key,
                        "payer": self.provider.wallet.public_key,
                        "zeta_program": self.exchange.program_id,
                    }
                )
            )
        # Create margin account if user doesn't have one
        if not self.margin_account._is_initialized:
            self._logger.info("User has no cross-margin account manager, creating one...")
            tx.add(
                initialize_cross_margin_account(
                    {"subaccount_index": subaccount_index},
                    {
                        "cross_margin_account": self.margin_account.address,
                        "cross_margin_account_manager": self._margin_account_manager_address,
                        "authority": self.provider.wallet.public_key,
                        "payer": self.provider.wallet.public_key,
                        "zeta_program": self.exchange.program_id,
                    },
                )
            )
        # Check they have an existing USDC account
        if await self._check_user_usdc_account_exists():
            tx.add(
                deposit_v2(
                    {"amount": utils.convert_decimal_to_fixed_int(amount)},
                    {
                        "margin_account": self.margin_account.address,
                        "vault": self._combined_vault_address,
                        "user_token_account": self._user_usdc_address,
                        "socialized_loss_account": self._combined_socialized_loss_address,
                        "authority": self.provider.wallet.public_key,
                        "state": self.exchange.state.address,
                        "pricing": self.exchange.pricing.address,
                    },
                )
            )
        else:
            raise Exception("User has no USDC, cannot deposit to margin account")

        # TODO: prefetch blockhash (look into blockhash cache)
        # recent_blockhash = await self.connection.get_latest_blockhash()
        # self._blockhash_cache.set(recent_blockhash.value.blockhash, recent_blockhash.context.slot)
        # tx.recent_blockhash = self._blockhash_cache.get()
        # signed_tx = self.provider.wallet.sign_transaction(tx)
        # TODO: investigate skip_confirmation=True effect in txOpts
        # signature = await self.provider.send(
        #     signed_tx,
        # )
        resp = await self.connection.send_transaction(tx, self.provider.wallet.payer)
        signature = resp.value
        self._logger.info(f"Deposit of ${amount} USDC to margin account {self.margin_account.address} submitted")
        return signature

    # TODO: withdraw (and optionally close)
    async def withdraw(self):
        raise NotImplementedError

    # TODO: placeorder
    async def place_order(
        self, asset: Asset, price: float, size: float, side: Side, order_opts: OrderOptions = OrderOptions
    ):
        if asset not in self.open_orders:
            raise Exception(f"Asset {asset.name} not loaded into client, cannot place order")
        tx = Transaction()
        if self.open_orders[asset] is None:
            self._logger.info("User has no open orders account, creating one...")
            tx.add(
                initialize_open_orders_v3(
                    {"asset": asset.to_program_type()},
                    {
                        "state": self.exchange.state.address,
                        "dex_program": constants.DEX_PID[self.network],
                        "system_program": SYS_PROGRAM_ID,
                        "open_orders": self._open_orders_addresses[asset],
                        "cross_margin_account": self.margin_account.address,
                        "authority": self.provider.wallet.public_key,
                        "payer": self.provider.wallet.public_key,
                        "market": self.exchange.markets[asset].address,
                        "rent": RENT,
                        "serum_authority": self.exchange._serum_authority_address,
                        "open_orders_map": pda.get_open_orders_map_address(
                            self.exchange.program_id, self._open_orders_addresses[asset]
                        ),
                    },
                )
            )
        tx.add(
            place_perp_order_v3(
                {
                    "price": utils.convert_decimal_to_fixed_int(price),
                    "size": utils.convert_decimal_to_fixed_lot(size),
                    "side": side.to_program_type(),
                    "order_type": order_opts.order_type.to_program_type(),
                    "client_order_id": order_opts.client_order_id,
                    "tif_offset": None,  # TODO: this later `getTIFOffset`
                    "tag": order_opts.tag,
                    "asset": asset.to_program_type(),
                },
                {
                    "state": self.exchange.state.address,
                    "pricing": self.exchange.pricing.address,
                    "margin_account": self.margin_account.address,
                    "authority": self.provider.wallet.public_key,
                    "dex_program": constants.DEX_PID[self.network],
                    "token_program": TOKEN_PROGRAM_ID,
                    "serum_authority": self.exchange._serum_authority_address,
                    "open_orders": self._open_orders_addresses[asset],
                    "rent": RENT,
                    "market_accounts": {
                        "market": self.exchange.markets[asset].address,
                        "request_queue": self.exchange.markets[asset]._serum_market.state.request_queue(),
                        "event_queue": self.exchange.markets[asset]._serum_market.state.event_queue(),
                        "bids": self.exchange.markets[asset]._serum_market.state.bids(),
                        "asks": self.exchange.markets[asset]._serum_market.state.asks(),
                        "coin_vault": self.exchange.markets[asset]._serum_market.state.coin(),
                        "pc_vault": ,
                        "order_payer_token_account": ,
                        "coin_wallet": ,
                        "pc_wallet": ,
                    },
                    "oracle": ,
                    "oracle_backup_feed": ,
                    "oracle_backup_program": ,
                    "market_mint": ,
                    "mint_authority": ,
                    "perp_sync_queue": ,
                },
            )
        )
        raise NotImplementedError

    # TODO: cancelorder
    async def cancel_order(self):
        raise NotImplementedError

    # TODO: cancelorderbyclientorderid

    # TODO: cancelallorders

    # TODO: cancelplace

    # TODO: liquidate
    async def liquidate(self):
        raise NotImplementedError
