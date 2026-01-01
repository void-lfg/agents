"""
Wallet operations for Polygon blockchain.

Handles balance checks, token approvals, and transaction signing.
"""

from decimal import Decimal
from typing import Optional

from web3 import Web3
from eth_account import Account
import structlog

from void.config import config

logger = structlog.get_logger()

# Contract addresses on Polygon
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_CONTRACT = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

# ERC20 ABI (partial)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]

# ERC1155 ABI (partial)
ERC1155_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_operator", "type": "address"},
            {"name": "_approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "type": "function",
    },
]


class WalletOperations:
    """
    Wallet operations for Polygon blockchain.

    Handles:
    - Balance queries
    - Token approvals
    - Transaction preparation
    """

    def __init__(self):
        # Connect to Polygon
        self.w3 = Web3(Web3.HTTPProvider(config.polygon.rpc_url))

        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Polygon RPC")

        logger.info(
            "wallet_operations_initialized",
            chain_id=self.w3.eth.chain_id,
        )

    def generate_private_key(self) -> str:
        """
        Generate a new private key.

        Returns:
            Hex-encoded private key
        """
        account = Account.create()
        logger.info(
            "private_key_generated",
            address=account.address,
        )
        return account.key.hex()

    def get_address(self, private_key: str) -> str:
        """
        Get wallet address from private key.

        Args:
            private_key: Hex-encoded private key

        Returns:
            Wallet address
        """
        account = Account.from_key(private_key)
        return account.address

    async def get_usdc_balance(
        self,
        address: str,
    ) -> Decimal:
        """
        Get USDC balance for address.

        Args:
            address: Wallet address

        Returns:
            USDC balance (6 decimals)
        """
        try:
            # Initialize contract
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(USDC_CONTRACT),
                abi=ERC20_ABI,
            )

            # Get balance (returns wei, need to convert to USDC decimals)
            balance_wei = contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()

            # USDC uses 6 decimals
            balance = Decimal(balance_wei) / Decimal(10 ** 6)

            return balance

        except Exception as e:
            logger.error(
                "usdc_balance_check_failed",
                address=address,
                error=str(e),
            )
            raise

    async def get_matic_balance(
        self,
        address: str,
    ) -> Decimal:
        """
        Get MATIC balance for address.

        Args:
            address: Wallet address

        Returns:
            MATIC balance (18 decimals)
        """
        try:
            # Get balance in wei
            balance_wei = self.w3.eth.get_balance(address)

            # Convert to MATIC (18 decimals)
            balance = Decimal(balance_wei) / Decimal(10 ** 18)

            return balance

        except Exception as e:
            logger.error(
                "matic_balance_check_failed",
                address=address,
                error=str(e),
            )
            raise

    def build_approval_tx(
        self,
        private_key: str,
        token_address: str,
        spender_address: str,
        amount: Optional[int] = None,
    ) -> dict:
        """
        Build token approval transaction.

        Args:
            private_key: Wallet private key
            token_address: Token contract address
            spender_address: Spender contract address
            amount: Amount to approve (None = max uint256)

        Returns:
            Transaction dictionary
        """
        try:
            account = Account.from_key(private_key)

            # Initialize token contract
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI,
            )

            # Build transaction
            if amount is None:
                # Max uint256
                amount = 2 ** 256 - 1

            nonce = self.w3.eth.get_transaction_count(account.address)

            transaction = contract.functions.approve(
                Web3.to_checksum_address(spender_address),
                amount,
            ).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'gas': 100000,  # Estimate gas
                'gasPrice': int(self.w3.eth.gas_price * config.polygon.gas_price_multiplier),
            })

            return transaction

        except Exception as e:
            logger.error("approval_tx_build_failed", error=str(e))
            raise

    def build_erc1155_approval_tx(
        self,
        private_key: str,
        operator_address: str,
    ) -> dict:
        """
        Build ERC1155 setApprovalForAll transaction.

        Args:
            private_key: Wallet private key
            operator_address: Operator to approve

        Returns:
            Transaction dictionary
        """
        try:
            account = Account.from_key(private_key)

            # Initialize CTF contract
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CTF_CONTRACT),
                abi=ERC1155_ABI,
            )

            nonce = self.w3.eth.get_transaction_count(account.address)

            transaction = contract.functions.setApprovalForAll(
                Web3.to_checksum_address(operator_address),
                True,
            ).build_transaction({
                'from': account.address,
                'nonce': nonce,
                'gas': 100000,
                'gasPrice': int(self.w3.eth.gas_price * config.polygon.gas_price_multiplier),
            })

            return transaction

        except Exception as e:
            logger.error("erc1155_approval_build_failed", error=str(e))
            raise

    def sign_transaction(
        self,
        private_key: str,
        transaction: dict,
    ) -> str:
        """
        Sign transaction with private key.

        Args:
            private_key: Wallet private key
            transaction: Transaction dictionary

        Returns:
            Raw signed transaction (hex)
        """
        try:
            account = Account.from_key(private_key)

            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(
                transaction,
                account.key,
            )

            return signed_tx.rawTransaction.hex()

        except Exception as e:
            logger.error("tx_sign_failed", error=str(e))
            raise


__all__ = ["WalletOperations"]
