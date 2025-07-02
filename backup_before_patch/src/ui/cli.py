"""
Enhanced CLI UI for the Solana pump.fun sniping bot.
Fixed version with proper layout structure and no justify errors.
"""
# File Location: src/ui/cli.py

import asyncio
from typing import List, Dict, Any, Optional
import time
from datetime import datetime
from dataclasses import dataclass
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich import box
from rich.align import Align

from src.utils.config import config_manager
from src.utils.logger import get_logger
from src.core.wallet_manager import wallet_manager
from src.core.connection_manager import connection_manager

logger = get_logger("cli_ui")
console = Console()


@dataclass
class Trade:
    """Represents a trade executed by the bot."""
    trade_type: str
    token_address: str
    amount: float
    price: float
    timestamp: float
    pnl: float = 0.0


class BotCLI:
    """Enhanced CLI UI for the Solana pump.fun sniping bot."""
    
    def __init__(self):
        self.layout = Layout()
        self.live = None
        self.running = False
        
        # Data storage
        self.tracked_wallet_activity = deque(maxlen=10)
        self.bot_actions = deque(maxlen=10)
        self.trades: List[Trade] = []
        self.token_holdings: Dict[str, Dict[str, float]] = {}
        
        # Statistics
        self.wallet_balance = 0.0
        self.initial_balance = 0.0
        self.performance_history = deque(maxlen=50)
        
        self.stats = {
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_volume": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "win_rate": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "buy_signals": 0,
            "transactions_monitored": 0,
            "connection_status": "🔴 Disconnected",
            "websocket_status": "🔴 Disconnected",
            "last_update": time.time()
        }
        
        self._setup_layout()
    
    def _setup_layout(self):
        """Setup the enhanced layout for the CLI UI."""
        # Main layout structure
        self.layout.split(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=4)
        )
        
        # Header
        self._update_header()
        
        # Body - reorganized for better readability
        body = self.layout["body"]
        body.split_column(
            Layout(name="top_row", size=15),    # Stats and tracking
            Layout(name="middle_row", ratio=1), # Activity and holdings
            Layout(name="bottom_row", size=12)  # Trades
        )
        
        # Top row - Stats and Tracking side by side
        body["top_row"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="tracking", ratio=1)
        )
        
        # Middle row - Activity and Holdings
        body["middle_row"].split_row(
            Layout(name="activity", ratio=2),
            Layout(name="holdings", ratio=1)
        )
        
        # FIXED: Bottom row should contain trades directly, not a nested layout
        # No need for body["bottom_row"]["trades"], just body["bottom_row"]
        
        # Initialize all panels
        self._initialize_panels()
    
    def _update_header(self):
        """Update header with title and status."""
        status_color = "green" if self.running else "red"
        
        # Create text with justify set on the Text object
        header_text = Text(justify="center")
        header_text.append("🚀 ", style="bold")
        header_text.append("SOLANA PUMP.FUN SNIPER BOT", style="bold cyan")
        header_text.append(" 🚀\n", style="bold")
        header_text.append(f"Status: {'RUNNING' if self.running else 'STOPPED'}", style=f"bold {status_color}")
        header_text.append(" | ", style="dim")
        header_text.append(f"Balance: {self.wallet_balance:.6f} SOL", style="bold yellow")
        
        self.layout["header"].update(
            Panel(
                Align.center(header_text),
                border_style="cyan",
                box=box.DOUBLE
            )
        )
    
    def _update_footer(self):
        """Update footer with connection status and controls."""
        footer_text = Text(justify="center")
        footer_text.append("RPC: ", style="dim")
        footer_text.append(self.stats['connection_status'], style="bold")
        footer_text.append(" | ", style="dim")
        footer_text.append("Monitor: ", style="dim")
        footer_text.append(self.stats['websocket_status'], style="bold")
        footer_text.append("\n")
        footer_text.append("Press ", style="dim")
        footer_text.append("Ctrl+C", style="bold yellow")
        footer_text.append(" to stop", style="dim")
        
        self.layout["footer"].update(
            Panel(
                Align.center(footer_text),
                border_style="dim",
                box=box.ROUNDED
            )
        )
    
    def _initialize_panels(self):
        """Initialize all UI panels with default content."""
        body = self.layout["body"]
        
        # Stats panel
        body["top_row"]["stats"].update(self._render_stats())
        
        # Tracking panel
        body["top_row"]["tracking"].update(self._render_tracking())
        
        # Activity panel
        body["middle_row"]["activity"].update(self._render_activity())
        
        # Holdings panel
        body["middle_row"]["holdings"].update(self._render_holdings())
        
        # FIXED: Trades panel - update bottom_row directly
        body["bottom_row"].update(self._render_trades())
        
        # Footer
        self._update_footer()
    
    def _render_stats(self) -> Panel:
        """Render statistics panel."""
        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column("Stat", style="bright_cyan", width=20)
        stats_table.add_column("Value", style="white", justify="right")
        
        total_pnl = self.stats["realized_pnl"] + self.stats["unrealized_pnl"]
        pnl_color = "bright_green" if total_pnl >= 0 else "bright_red"
        
        stats_data = [
            ("💰 Wallet Balance", f"{self.wallet_balance:.6f} SOL"),
            ("📊 Total PnL", Text(f"{total_pnl:+.6f} SOL", style=pnl_color)),
            ("📈 Win Rate", f"{self.stats['win_rate']:.1f}%"),
            ("", ""),
            ("🎯 Total Trades", str(self.stats["total_trades"])),
            ("✅ Successful", str(self.stats["successful_trades"])),
            ("❌ Failed", str(self.stats["failed_trades"])),
            ("", ""),
            ("💎 Best Trade", f"{self.stats['best_trade']:.6f} SOL"),
            ("💸 Worst Trade", f"{self.stats['worst_trade']:.6f} SOL"),
            ("📡 Buy Signals", str(self.stats["buy_signals"])),
        ]
        
        for label, value in stats_data:
            if label:
                if isinstance(value, Text):
                    stats_table.add_row(label, value)
                else:
                    stats_table.add_row(label, value)
            else:
                stats_table.add_row("", "")
        
        return Panel(
            stats_table,
            title="📊 Bot Statistics",
            title_align="left",
            border_style="bright_blue",
            box=box.ROUNDED
        )
    
    def _render_tracking(self) -> Panel:
        """Render wallet tracking information."""
        tracking_table = Table(show_header=False, box=None, padding=(0, 2))
        tracking_table.add_column("Label", style="bright_cyan", width=20)
        tracking_table.add_column("Value", style="white", justify="right")
        
        tracker_stats = {}
        try:
            from src.monitoring.wallet_tracker import wallet_tracker
            if wallet_tracker:
                tracker_stats = wallet_tracker.get_stats()
        except:
            pass
        
        # Get polling interval from wallet tracker
        polling_interval = "0.5s"  # Default
        try:
            from src.monitoring.wallet_tracker import wallet_tracker
            if wallet_tracker and hasattr(wallet_tracker, 'POLL_INTERVAL'):
                polling_interval = f"{wallet_tracker.POLL_INTERVAL}s"
        except:
            pass
        
        tracking_data = [
            ("⚡ Poll Interval", polling_interval),
            ("🔍 Transactions", f"{tracker_stats.get('transactions_detected', 0)}"),
            ("🟢 Buys Detected", f"{tracker_stats.get('buys_detected', 0)}"),
            ("🔴 Sells Detected", f"{tracker_stats.get('sells_detected', 0)}"),
            ("⚠️ Errors", f"{tracker_stats.get('errors', 0)}"),
            ("", ""),
            ("📍 Active Wallets", ""),
        ]
        
        for label, value in tracking_data:
            if label:
                tracking_table.add_row(label, value)
            else:
                tracking_table.add_row("", "")
        
        settings = config_manager.get_settings()
        for i, wallet in enumerate(settings.tracking.wallets[:3]):
            wallet_display = f"{wallet[:6]}...{wallet[-4:]}"
            tracking_table.add_row(f"  #{i+1}", wallet_display)
        
        return Panel(
            tracking_table,
            title="🎯 Wallet Tracking",
            title_align="left",
            border_style="bright_blue",
            box=box.ROUNDED
        )
    
    def _render_activity(self) -> Panel:
        """Render activity feed."""
        activity_table = Table(
            show_header=True,
            header_style="bold bright_yellow",
            box=box.SIMPLE,
            padding=(0, 1),
            expand=True
        )
        activity_table.add_column("Time", style="dim", width=10)
        activity_table.add_column("Event", style="white", width=20)
        activity_table.add_column("Details", style="bright_cyan")
        
        all_activity = []
        
        for activity in self.tracked_wallet_activity:
            all_activity.append(("wallet", activity))
        
        for action in self.bot_actions:
            all_activity.append(("bot", action))
        
        all_activity.sort(key=lambda x: x[1].get("timestamp", 0), reverse=True)
        
        for activity_type, activity in all_activity[:8]:
            time_str = datetime.fromtimestamp(activity.get("timestamp", 0)).strftime("%H:%M:%S")
            
            if activity_type == "wallet":
                event = f"👁️ {activity.get('action', 'Unknown')}"
                wallet_addr = activity.get('wallet', '')[:8] + "..."
                token_addr = activity.get('token', '')[:8] + "..."
                amount = activity.get('amount', 0)
                details = f"{wallet_addr} → {token_addr} ({amount:.4f} SOL)"
            else:
                event = f"🤖 {activity.get('action', 'Unknown')}"
                details = activity.get('details', '')
            
            activity_table.add_row(time_str, event, details)
        
        if not all_activity:
            activity_table.add_row("--:--:--", "Waiting for activity...", "")
        
        return Panel(
            activity_table,
            title="🔔 Live Activity Feed",
            title_align="left",
            border_style="bright_yellow",
            box=box.ROUNDED
        )
    
    def _render_holdings(self) -> Panel:
        """Render current holdings."""
        holdings_table = Table(
            show_header=True,
            header_style="bold bright_green",
            box=box.SIMPLE,
            padding=(0, 1)
        )
        holdings_table.add_column("Token", width=15)
        holdings_table.add_column("Amount", width=12, justify="right")
        holdings_table.add_column("PnL%", width=10, justify="right")
        
        active_holdings = [(t, h) for t, h in self.token_holdings.items() if h["amount"] > 0]
        
        for token, holding in active_holdings[:5]:
            current_price = holding.get("current_price", holding["avg_price"])
            pnl_percent = ((current_price - holding["avg_price"]) / holding["avg_price"] * 100) if holding["avg_price"] > 0 else 0
            pnl_color = "bright_green" if pnl_percent >= 0 else "bright_red"
            
            holdings_table.add_row(
                f"{token[:8]}...",
                f"{holding['amount']:.4f}",
                Text(f"{pnl_percent:+.1f}%", style=pnl_color)
            )
        
        if not active_holdings:
            holdings_table.add_row("No active positions", "-", "-")
        
        return Panel(
            holdings_table,
            title="💼 Current Holdings",
            title_align="left",
            border_style="bright_green",
            box=box.ROUNDED
        )
    
    def _render_trades(self) -> Panel:
        """Render recent trades."""
        trades_table = Table(
            show_header=True,
            header_style="bold bright_magenta",
            box=box.SIMPLE,
            padding=(0, 1),
            expand=True
        )
        trades_table.add_column("Time", style="dim", width=10)
        trades_table.add_column("Type", width=8)
        trades_table.add_column("Token", width=15)
        trades_table.add_column("Amount", width=12, justify="right")
        trades_table.add_column("Price", width=12, justify="right")
        trades_table.add_column("PnL", width=12, justify="right")
        
        for trade in self.trades[-6:]:
            time_str = datetime.fromtimestamp(trade.timestamp).strftime("%H:%M:%S")
            type_color = "bright_green" if trade.trade_type == "BUY" else "bright_red"
            pnl_color = "bright_green" if trade.pnl >= 0 else "bright_red"
            
            trades_table.add_row(
                time_str,
                Text(trade.trade_type, style=type_color),
                f"{trade.token_address[:8]}...",
                f"{trade.amount:.4f}",
                f"{trade.price:.8f}",
                Text(f"{trade.pnl:+.6f}", style=pnl_color) if trade.pnl != 0 else "-"
            )
        
        if not self.trades:
            trades_table.add_row("--:--:--", "-", "No trades executed yet", "-", "-", "-")
        
        return Panel(
            trades_table,
            title="💹 Recent Trades",
            title_align="left",
            border_style="bright_magenta",
            box=box.ROUNDED
        )
    
    def _update_ui(self):
        """Update all UI components."""
        try:
            self._update_header()
            
            body = self.layout["body"]
            body["top_row"]["stats"].update(self._render_stats())
            body["top_row"]["tracking"].update(self._render_tracking())
            body["middle_row"]["activity"].update(self._render_activity())
            body["middle_row"]["holdings"].update(self._render_holdings())
            # FIXED: Update bottom_row directly, not bottom_row["trades"]
            body["bottom_row"].update(self._render_trades())
            
            self._update_footer()
            
        except Exception as e:
            logger.error(f"Error updating UI: {e}")
    
    async def _update_balance(self):
        """Update wallet balance periodically."""
        await asyncio.sleep(2)
        
        first_update = True
        
        while self.running:
            try:
                balance = await wallet_manager.get_balance()
                self.wallet_balance = balance
                
                if first_update:
                    self.initial_balance = balance
                    first_update = False
                
                total_pnl = self.stats["realized_pnl"] + self.stats["unrealized_pnl"]
                self.performance_history.append(total_pnl)
                
                rpc_connected = await self._check_rpc_connection()
                self.stats["connection_status"] = "🟢 Connected" if rpc_connected else "🔴 Disconnected"
                
                try:
                    from src.monitoring.wallet_tracker import wallet_tracker
                    if wallet_tracker and hasattr(wallet_tracker, 'is_monitoring_active') and wallet_tracker.is_monitoring_active():
                        self.stats["websocket_status"] = "🟢 Active"
                    else:
                        self.stats["websocket_status"] = "🔴 Inactive"
                except:
                    self.stats["websocket_status"] = "⚠️ Unknown"
                
                self.stats["last_update"] = time.time()
                
                if self.live:
                    self._update_ui()
                    
            except Exception as e:
                logger.error(f"Error updating balance: {e}")
                
            await asyncio.sleep(3)
    
    async def _check_rpc_connection(self) -> bool:
        """Check if RPC connection is active."""
        try:
            client = await connection_manager.get_rpc_client()
            if client:
                await client.get_slot()
                return True
        except:
            pass
        return False
    
    def register_callbacks(self):
        """Register callbacks for bot events."""
        try:
            from src.monitoring.wallet_tracker import wallet_tracker
            from src.trading.strategy_engine import strategy_engine
            
            if wallet_tracker:
                wallet_tracker.register_buy_callback(self._on_wallet_buy)
                logger.info("Registered wallet buy callback with UI")
                
            if strategy_engine:
                strategy_engine.register_trade_callback(self._on_bot_trade)
                logger.info("Registered trade callback with UI")
                
        except Exception as e:
            logger.error(f"Error registering callbacks: {e}")
    
    def _on_wallet_buy(self, wallet_address: str, token_address: str, amount_sol: float):
        """Callback for when a tracked wallet buys a token."""
        activity = {
            "timestamp": time.time(),
            "action": "Wallet Buy",
            "wallet": wallet_address,
            "token": token_address,
            "amount": amount_sol
        }
        self.tracked_wallet_activity.append(activity)
        self.stats["buy_signals"] += 1
        self.stats["transactions_monitored"] += 1
        
        if self.live:
            self._update_ui()
    
    def _on_bot_trade(self, trade_type: str, token_address: str, amount: float, price: float):
        """Callback for when the bot executes a trade."""
        trade = Trade(trade_type, token_address, amount, price, time.time())
        self.trades.append(trade)
        
        action = {
            "timestamp": time.time(),
            "action": f"Bot {trade_type}",
            "details": f"{token_address[:8]}... {amount:.4f} @ {price:.8f}"
        }
        self.bot_actions.append(action)
        
        self.stats["total_trades"] += 1
        self.stats["total_volume"] += amount * price
        
        if trade_type == "BUY":
            if token_address not in self.token_holdings:
                self.token_holdings[token_address] = {
                    "amount": 0,
                    "avg_price": 0,
                    "current_price": price
                }
            
            holding = self.token_holdings[token_address]
            total_amount = holding["amount"] + amount
            total_cost = (holding["amount"] * holding["avg_price"]) + (amount * price)
            holding["amount"] = total_amount
            holding["avg_price"] = total_cost / total_amount if total_amount > 0 else 0
            
        elif trade_type == "SELL":
            if token_address in self.token_holdings:
                holding = self.token_holdings[token_address]
                profit = (price - holding["avg_price"]) * amount
                trade.pnl = profit
                
                self.stats["realized_pnl"] += profit
                
                if profit > 0:
                    self.stats["successful_trades"] += 1
                    self.stats["best_trade"] = max(self.stats["best_trade"], profit)
                else:
                    self.stats["failed_trades"] += 1
                    self.stats["worst_trade"] = min(self.stats["worst_trade"], profit)
                
                holding["amount"] -= amount
                if holding["amount"] <= 0:
                    del self.token_holdings[token_address]
        
        if self.stats["total_trades"] > 0:
            self.stats["win_rate"] = (self.stats["successful_trades"] / self.stats["total_trades"]) * 100
        
        if self.live:
            self._update_ui()
    
    async def start(self):
        """Start the CLI UI."""
        self.running = True
        self._update_header()
        
        self.register_callbacks()
        
        asyncio.create_task(self._update_balance())
        
        logger.info("Starting UI live display")
        with Live(self.layout, refresh_per_second=4, screen=True) as live:
            self.live = live
            logger.info("UI live display started")
            
            while self.running:
                await asyncio.sleep(0.25)
    
    def stop(self):
        """Stop the CLI UI."""
        self.running = False
        if self.live:
            self.live.stop()
        
        self._update_header()


# Global CLI UI instance
bot_cli = None

def initialize_bot_cli():
    """Initialize the global bot CLI instance."""
    global bot_cli
    bot_cli = BotCLI()
    return bot_cli
