"""
Enhanced wallet tracking with rate limiting for DRPC.
Monitors wallets without hitting rate limits.
"""
# File Location: src/monitoring/wallet_tracker.py

import asyncio
from typing import Dict, Any, Optional, Callable, List, Set
import json
from datetime import datetime
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.commitment import Confirmed
import base58
import time
from solders.signature import Signature

from src.utils.config import config_manager
from src.utils.logger import get_logger
from src.core.connection_manager import connection_manager

logger = get_logger("wallet_tracker")


class WalletTracker:
    """
    Wallet tracker with intelligent rate limiting for DRPC.
    """
    
    def __init__(self):
        self.settings = config_manager.get_settings()
        self.tracked_wallets: Set[str] = set(self.settings.tracking.wallets)
        self.pump_program_id = PublicKey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
        self.processed_signatures: Set[str] = set()
        self.running = False
        self.monitoring_active = False
        self.buy_callbacks: List[Callable] = []
        self.monitoring_tasks: List[asyncio.Task] = []
        
        # DEX Program IDs
        self.DEX_PROGRAMS = {
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
            "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter", 
            "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter",
            "JUP3c2Uh3WA4Ng34tw6kPd2G4C5BB21Xo36Je1s32Ph": "Jupiter",
            "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
            "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca",
            "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora",
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
            "9tKE7Mbmj4mxDjWatikzGMszEyKWiuNksioVe4dFAFxF": "OKX DEX",
            "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "Phoenix"
        }
        
        # RATE LIMITING SETTINGS
        self.poll_interval = 2.0  # Poll every 2 seconds (slower to avoid rate limits)
        self.max_signatures_per_poll = 5  # Fewer signatures per request
        self.rate_limit_delay = 5.0  # Delay after rate limit error
        self.max_requests_per_minute = 20  # Conservative limit for DRPC
        self.request_times: List[float] = []
        
        # Stats
        self.stats = {
            "transactions_detected": 0,
            "buys_detected": 0,
            "errors": 0,
            "rate_limit_hits": 0,
            "last_poll": None
        }
        
        logger.info(f"Wallet tracker initialized - tracking {len(self.tracked_wallets)} wallet(s)")
        logger.info(f"Using DRPC endpoint with rate limiting")
    
    async def start(self) -> None:
        """Start tracking wallets."""
        if self.running:
            logger.warning("Wallet tracker already running")
            return
            
        if not self.tracked_wallets:
            logger.info("No wallets specified for tracking")
            return
            
        self.running = True
        self.monitoring_active = True
        logger.info(f"Starting wallet tracker for: {list(self.tracked_wallets)}")
        
        # Start monitoring task for each wallet
        for wallet_address in self.tracked_wallets:
            task = asyncio.create_task(self._monitor_wallet(wallet_address))
            self.monitoring_tasks.append(task)
            logger.info(f"Started monitoring wallet: {wallet_address}")
    
    async def stop(self) -> None:
        """Stop tracking wallets."""
        self.running = False
        self.monitoring_active = False
        
        # Cancel all monitoring tasks
        for task in self.monitoring_tasks:
            task.cancel()
        
        await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
        self.monitoring_tasks.clear()
        
        logger.info("Wallet tracker stopped")
    
    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        current_time = time.time()
        
        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if current_time - t < 60]
        
        # If we've made too many requests, wait
        if len(self.request_times) >= self.max_requests_per_minute:
            wait_time = 60 - (current_time - self.request_times[0])
            if wait_time > 0:
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.request_times = []
        
        # Record this request
        self.request_times.append(current_time)
    
    async def _monitor_wallet(self, wallet_address: str) -> None:
        """Monitor a wallet for transactions with rate limiting."""
        logger.info(f"Monitoring wallet: {wallet_address}")
        consecutive_errors = 0
        
        while self.running:
            try:
                # Check rate limit before making request
                await self._check_rate_limit()
                
                # Get RPC client
                client = await connection_manager.get_rpc_client()
                if not client:
                    await asyncio.sleep(5)
                    continue
                
                # Get recent signatures
                pubkey = PublicKey.from_string(wallet_address)
                response = await client.get_signatures_for_address(
                    pubkey,
                    limit=self.max_signatures_per_poll,
                    commitment=Confirmed
                )
                
                if response and hasattr(response, 'value') and response.value:
                    # Process each signature
                    for sig_info in response.value:
                        if hasattr(sig_info, 'signature'):
                            signature_str = str(sig_info.signature)
                            
                            # Skip if already processed
                            if signature_str in self.processed_signatures:
                                continue
                            
                            # Process new transaction
                            self.processed_signatures.add(signature_str)
                            
                            # Keep cache size manageable
                            if len(self.processed_signatures) > 500:
                                self.processed_signatures = set(
                                    list(self.processed_signatures)[-250:]
                                )
                            
                            # Add small delay between transaction analyses
                            await asyncio.sleep(0.1)
                            
                            # Analyze the transaction
                            await self._analyze_transaction(
                                client,
                                signature_str,
                                wallet_address
                            )
                
                # Update stats
                self.stats["last_poll"] = time.time()
                consecutive_errors = 0
                
                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_msg or "Too Many Requests" in error_msg:
                    self.stats["rate_limit_hits"] += 1
                    logger.warning(f"Rate limit hit! Waiting {self.rate_limit_delay}s...")
                    await asyncio.sleep(self.rate_limit_delay)
                else:
                    logger.error(f"Error monitoring wallet {wallet_address}: {error_msg}")
                    self.stats["errors"] += 1
                    
                    # Exponential backoff on errors
                    wait_time = min(30, 2 ** consecutive_errors)
                    await asyncio.sleep(wait_time)
    
    async def _analyze_transaction(
        self, 
        client: Any,
        signature: str, 
        wallet_address: str
    ) -> None:
        """Analyze a transaction to detect DEX trades."""
        try:
            # Check rate limit before transaction fetch
            await self._check_rate_limit()
            
            # Get full transaction
            tx_response = await client.get_transaction(
                Signature.from_string(signature),
                encoding="jsonParsed",
                commitment=Confirmed,
                max_supported_transaction_version=0
            )
            
            if not tx_response or not hasattr(tx_response, 'value') or not tx_response.value:
                return
            
            tx_data = tx_response.value
            
            # Convert to dict if needed
            if hasattr(tx_data, 'to_json'):
                tx_json = tx_data.to_json()
                tx_data = json.loads(tx_json)
            
            # Check if transaction succeeded
            meta = tx_data.get("meta", {})
            if meta.get("err"):
                return
            
            # Get transaction details
            transaction = tx_data.get("transaction", {})
            message = transaction.get("message", {})
            instructions = message.get("instructions", [])
            
            # Check each instruction
            for instruction in instructions:
                program_id = instruction.get("programId", "")
                
                # Check if it's a DEX interaction
                if program_id in self.DEX_PROGRAMS:
                    platform = self.DEX_PROGRAMS[program_id]
                    
                    # Analyze for buy/sell
                    result = await self._parse_dex_instruction(
                        instruction, 
                        meta, 
                        platform,
                        wallet_address
                    )
                    
                    if result and result.get("is_buy"):
                        # Detected a buy!
                        token_address = result.get("token_address", "Unknown")
                        amount_sol = result.get("amount_sol", 0)
                        
                        logger.info(f"="*60)
                        logger.info(f"🟢 BUY DETECTED!")
                        logger.info(f"Platform: {platform}")
                        logger.info(f"Wallet: {wallet_address[:8]}...")
                        logger.info(f"Token: {token_address}")
                        logger.info(f"Amount: {amount_sol:.6f} SOL")
                        logger.info(f"TX: https://solscan.io/tx/{signature}")
                        logger.info(f"="*60)
                        
                        self.stats["transactions_detected"] += 1
                        self.stats["buys_detected"] += 1
                        
                        # Notify callbacks
                        await self._notify_buy_callbacks(
                            wallet_address,
                            token_address,
                            amount_sol,
                            platform,
                            f"https://solscan.io/tx/{signature}"
                        )
                        
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                self.stats["rate_limit_hits"] += 1
                logger.warning(f"Rate limit hit analyzing transaction {signature[:8]}...")
                await asyncio.sleep(self.rate_limit_delay)
            else:
                logger.error(f"Error analyzing transaction {signature}: {error_msg}")
                self.stats["errors"] += 1
    
    async def _parse_dex_instruction(
        self,
        instruction: Dict,
        meta: Dict,
        platform: str,
        wallet_address: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a DEX instruction to detect buys."""
        try:
            # Get balance changes
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            
            # Get account keys
            account_keys = meta.get("postTokenBalances", [])
            
            # Look for SOL decrease (indicating a buy)
            if pre_balances and post_balances and len(pre_balances) == len(post_balances):
                # Check first few accounts (usually where wallet is)
                for i in range(min(5, len(pre_balances))):
                    sol_change = (post_balances[i] - pre_balances[i]) / 1e9
                    
                    if sol_change < -0.0001:  # SOL decreased (likely a buy)
                        # Try to find token info
                        token_mint = "Unknown"
                        for token_balance in account_keys:
                            if token_balance.get("uiTokenAmount", {}).get("uiAmount", 0) > 0:
                                token_mint = token_balance.get("mint", "Unknown")
                                break
                        
                        return {
                            "is_buy": True,
                            "token_address": token_mint,
                            "amount_sol": abs(sol_change),
                            "platform": platform
                        }
            
            # Check parsed instruction
            parsed = instruction.get("parsed", {})
            if parsed and parsed.get("type") in ["swap", "swapBaseIn"]:
                info = parsed.get("info", {})
                return {
                    "is_buy": True,
                    "token_address": info.get("mint", "Unknown"),
                    "amount_sol": 0.001,  # Default amount
                    "platform": platform
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error parsing {platform} instruction: {e}")
            return None
    
    async def _notify_buy_callbacks(
        self,
        wallet_address: str,
        token_address: str,
        amount_sol: float,
        platform: str,
        tx_url: str
    ) -> None:
        """Notify all registered callbacks about a buy."""
        for callback in self.buy_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(wallet_address, token_address, amount_sol, platform, tx_url)
                else:
                    callback(wallet_address, token_address, amount_sol, platform, tx_url)
            except Exception as e:
                logger.error(f"Error in buy callback: {e}")
    
    def register_buy_callback(self, callback: Callable) -> None:
        """Register a callback for buy events."""
        self.buy_callbacks.append(callback)
        logger.info(f"Registered buy callback - Total: {len(self.buy_callbacks)}")
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is active."""
        return self.monitoring_active
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        return {
            **self.stats,
            "tracked_wallets": len(self.tracked_wallets),
            "processed_signatures": len(self.processed_signatures),
            "request_queue_size": len(self.request_times)
        }


# Global wallet tracker instance
wallet_tracker = None

def initialize_wallet_tracker():
    """Initialize the global wallet tracker instance."""
    global wallet_tracker
    wallet_tracker = WalletTracker()
    return wallet_tracker
