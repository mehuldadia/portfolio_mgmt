"""
Module for calculating capital gains using FIFO method with short-term/long-term classification.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class Position:
    """Represents a stock position (holding)."""
    symbol: str
    quantity: float
    price: float
    date: datetime
    fees: float = 0.0
    
    @property
    def total_cost(self) -> float:
        return (self.quantity * self.price) + self.fees


@dataclass
class CapitalGain:
    """Represents a capital gain/loss transaction."""
    symbol: str
    sell_date: datetime
    sell_quantity: float
    sell_price: float
    sell_fees: float
    buy_date: datetime
    buy_quantity: float
    buy_price: float
    buy_fees: float
    gain_loss: float
    is_short_term: bool
    holding_period_days: int
    
    @property
    def sell_total(self) -> float:
        return (self.sell_quantity * self.sell_price) - self.sell_fees
    
    @property
    def buy_total(self) -> float:
        return (self.buy_quantity * self.buy_price) + self.buy_fees


class GainsCalculator:
    """Calculates capital gains using FIFO method with tax classification."""
    
    def __init__(self, short_term_threshold_days: int = 365):
        """
        Initialize the gains calculator.
        
        Args:
            short_term_threshold_days (int): Number of days to classify as short-term (default: 365)
        """
        self.short_term_threshold_days = short_term_threshold_days
    
    def calculate_gains(self, transactions_df: pd.DataFrame) -> Tuple[List[CapitalGain], List[Position]]:
        """
        Calculate capital gains using FIFO method.
        
        Args:
            transactions_df (pd.DataFrame): DataFrame with transaction data
            
        Returns:
            Tuple[List[CapitalGain], List[Position]]: List of capital gains and remaining positions
        """
        # Sort transactions by date (TransactionReader uses Txn_Date)
        transactions_df = transactions_df.sort_values('Txn_Date').reset_index(drop=True)
        
        # Initialize tracking
        positions = {}  # symbol -> list of positions (FIFO queue)
        capital_gains = []
        
        for _, transaction in transactions_df.iterrows():
            symbol = transaction['Symbol']
            date = transaction['Txn_Date']
            quantity = transaction['Quantity']
            price = transaction['Price']
            fees = transaction.get('Fees', 0.0)
            transaction_type = transaction['Type']
            
            if transaction_type == 'BUY':
                # Add to positions
                if symbol not in positions:
                    positions[symbol] = []
                
                positions[symbol].append(Position(
                    symbol=symbol,
                    quantity=quantity,
                    price=price,
                    date=date,
                    fees=fees
                ))
                
            elif transaction_type == 'SELL':
                # Process sell transaction using FIFO
                remaining_sell_qty = quantity
                
                while remaining_sell_qty > 0 and symbol in positions and positions[symbol]:
                    # Get the oldest position (FIFO)
                    oldest_position = positions[symbol][0]
                    
                    # Calculate how much to sell from this position
                    sell_from_position = min(remaining_sell_qty, oldest_position.quantity)
                    
                    # Calculate proportional fees
                    proportional_fees = (sell_from_position / oldest_position.quantity) * oldest_position.fees
                    
                    # Create capital gain record
                    holding_period = (date - oldest_position.date).days
                    is_short_term = holding_period <= self.short_term_threshold_days
                    
                    # Calculate gain/loss
                    sell_value = sell_from_position * price
                    buy_value = sell_from_position * oldest_position.price
                    proportional_sell_fees = (sell_from_position / quantity) * fees
                    
                    gain_loss = sell_value - buy_value - proportional_sell_fees - proportional_fees
                    
                    capital_gain = CapitalGain(
                        symbol=symbol,
                        sell_date=date,
                        sell_quantity=sell_from_position,
                        sell_price=price,
                        sell_fees=proportional_sell_fees,
                        buy_date=oldest_position.date,
                        buy_quantity=sell_from_position,
                        buy_price=oldest_position.price,
                        buy_fees=proportional_fees,
                        gain_loss=gain_loss,
                        is_short_term=is_short_term,
                        holding_period_days=holding_period
                    )
                    
                    capital_gains.append(capital_gain)
                    
                    # Update position
                    oldest_position.quantity -= sell_from_position
                    oldest_position.fees -= proportional_fees
                    
                    # Remove position if fully sold
                    if oldest_position.quantity <= 0:
                        positions[symbol].pop(0)
                    
                    remaining_sell_qty -= sell_from_position
        
        # Convert remaining positions to list
        remaining_positions = []
        for symbol_positions in positions.values():
            remaining_positions.extend(symbol_positions)
        
        return capital_gains, remaining_positions
    
    def get_gains_summary(self, capital_gains: List[CapitalGain]) -> Dict[str, Any]:
        """
        Get summary statistics for capital gains.
        
        Args:
            capital_gains (List[CapitalGain]): List of capital gains
            
        Returns:
            Dict[str, Any]: Summary statistics
        """
        if not capital_gains:
            return {
                'total_gains': 0.0,
                'total_losses': 0.0,
                'net_gain': 0.0,
                'short_term_gains': 0.0,
                'short_term_losses': 0.0,
                'long_term_gains': 0.0,
                'long_term_losses': 0.0,
                'total_transactions': 0,
                'short_term_transactions': 0,
                'long_term_transactions': 0
            }
        
        df = pd.DataFrame([
            {
                'gain_loss': gain.gain_loss,
                'is_short_term': gain.is_short_term,
                'symbol': gain.symbol,
                'sell_date': gain.sell_date
            }
            for gain in capital_gains
        ])
        
        # Calculate totals
        total_gains = df[df['gain_loss'] > 0]['gain_loss'].sum()
        total_losses = abs(df[df['gain_loss'] < 0]['gain_loss'].sum())
        net_gain = total_gains - total_losses
        
        # Short-term vs Long-term
        short_term_df = df[df['is_short_term']]
        long_term_df = df[~df['is_short_term']]
        
        short_term_gains = short_term_df[short_term_df['gain_loss'] > 0]['gain_loss'].sum()
        short_term_losses = abs(short_term_df[short_term_df['gain_loss'] < 0]['gain_loss'].sum())
        long_term_gains = long_term_df[long_term_df['gain_loss'] > 0]['gain_loss'].sum()
        long_term_losses = abs(long_term_df[long_term_df['gain_loss'] < 0]['gain_loss'].sum())
        
        # Yearly breakdown
        df['year'] = df['sell_date'].dt.year
        yearly_breakdown = df.groupby('year').agg({
            'gain_loss': 'sum',
            'is_short_term': 'count'
        }).rename(columns={'is_short_term': 'transaction_count'}).to_dict('index')
        
        return {
            'total_gains': total_gains,
            'total_losses': total_losses,
            'net_gain': net_gain,
            'short_term_gains': short_term_gains,
            'short_term_losses': short_term_losses,
            'long_term_gains': long_term_gains,
            'long_term_losses': long_term_losses,
            'total_transactions': len(df),
            'short_term_transactions': len(short_term_df),
            'long_term_transactions': len(long_term_df),
            'yearly_breakdown': yearly_breakdown
        }
    
    def get_yearly_summary(self, capital_gains: List[CapitalGain]) -> Dict[int, Dict[str, Any]]:
        """
        Get yearly summary of capital gains.
        
        Args:
            capital_gains (List[CapitalGain]): List of capital gains
            
        Returns:
            Dict[int, Dict[str, Any]]: Yearly summary data
        """
        if not capital_gains:
            return {}
        
        df = pd.DataFrame([
            {
                'year': gain.sell_date.year,
                'gain_loss': gain.gain_loss,
                'is_short_term': gain.is_short_term,
                'symbol': gain.symbol,
                'sell_date': gain.sell_date
            }
            for gain in capital_gains
        ])
        
        yearly_summary = {}
        
        for year in sorted(df['year'].unique()):
            year_data = df[df['year'] == year]
            
            total_gains = year_data[year_data['gain_loss'] > 0]['gain_loss'].sum()
            total_losses = abs(year_data[year_data['gain_loss'] < 0]['gain_loss'].sum())
            net_gain = total_gains - total_losses
            
            short_term_data = year_data[year_data['is_short_term']]
            long_term_data = year_data[~year_data['is_short_term']]
            
            yearly_summary[year] = {
                'total_gains': total_gains,
                'total_losses': total_losses,
                'net_gain': net_gain,
                'short_term_gains': short_term_data[short_term_data['gain_loss'] > 0]['gain_loss'].sum(),
                'short_term_losses': abs(short_term_data[short_term_data['gain_loss'] < 0]['gain_loss'].sum()),
                'long_term_gains': long_term_data[long_term_data['gain_loss'] > 0]['gain_loss'].sum(),
                'long_term_losses': abs(long_term_data[long_term_data['gain_loss'] < 0]['gain_loss'].sum()),
                'transaction_count': len(year_data),
                'symbols_traded': year_data['symbol'].nunique()
            }
        
        return yearly_summary

