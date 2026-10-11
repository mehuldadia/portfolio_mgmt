"""
Module for exporting capital gains data to Excel files.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from .gains_calculator import CapitalGain, Position
import os


class ExcelExporter:
    """Handles exporting capital gains data to Excel files."""
    
    def __init__(self, output_dir: str = "output"):
        """
        Initialize the Excel exporter.
        
        Args:
            output_dir (str): Directory to save Excel files
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def export_capital_gains(self, 
                           capital_gains: List[CapitalGain], 
                           remaining_positions: List[Position],
                           filename: str = None) -> str:
        """
        Export capital gains and remaining positions to Excel file.
        
        Args:
            capital_gains (List[CapitalGain]): List of capital gains
            remaining_positions (List[Position]): List of remaining positions
            filename (str): Optional custom filename
            
        Returns:
            str: Path to the exported Excel file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capital_gains_report_{timestamp}.xlsx"
        
        filepath = os.path.join(self.output_dir, filename)
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Export capital gains
            if capital_gains:
                gains_df = self._create_gains_dataframe(capital_gains)
                gains_df.to_excel(writer, sheet_name='Capital_Gains', index=False)
            
            # Export remaining positions
            if remaining_positions:
                positions_df = self._create_positions_dataframe(remaining_positions)
                positions_df.to_excel(writer, sheet_name='Remaining_Positions', index=False)
            
            # Export summary
            summary_df = self._create_summary_dataframe(capital_gains)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Export yearly breakdown
            yearly_df = self._create_yearly_dataframe(capital_gains)
            if not yearly_df.empty:
                yearly_df.to_excel(writer, sheet_name='Yearly_Breakdown', index=False)
        
        return filepath
    
    def _create_gains_dataframe(self, capital_gains: List[CapitalGain]) -> pd.DataFrame:
        """Create DataFrame from capital gains list."""
        data = []
        for gain in capital_gains:
            data.append({
                'Symbol': gain.symbol,
                'Sell_Date': gain.sell_date.strftime('%Y-%m-%d'),
                'Sell_Quantity': gain.sell_quantity,
                'Sell_Price': gain.sell_price,
                'Sell_Total': gain.sell_total,
                'Sell_Fees': gain.sell_fees,
                'Buy_Date': gain.buy_date.strftime('%Y-%m-%d'),
                'Buy_Quantity': gain.buy_quantity,
                'Buy_Price': gain.buy_price,
                'Buy_Total': gain.buy_total,
                'Buy_Fees': gain.buy_fees,
                'Gain_Loss': gain.gain_loss,
                'Tax_Classification': 'Short-term' if gain.is_short_term else 'Long-term',
                'Holding_Period_Days': gain.holding_period_days
            })
        
        return pd.DataFrame(data)
    
    def _create_positions_dataframe(self, positions: List[Position]) -> pd.DataFrame:
        """Create DataFrame from remaining positions list."""
        data = []
        for position in positions:
            data.append({
                'Symbol': position.symbol,
                'Quantity': position.quantity,
                'Price': position.price,
                'Date': position.date.strftime('%Y-%m-%d'),
                'Fees': position.fees,
                'Total_Cost': position.total_cost
            })
        
        return pd.DataFrame(data)
    
    def _create_summary_dataframe(self, capital_gains: List[CapitalGain]) -> pd.DataFrame:
        """Create summary DataFrame."""
        if not capital_gains:
            return pd.DataFrame({
                'Metric': ['Total Gains', 'Total Losses', 'Net Gain', 'Short-term Gains', 
                          'Short-term Losses', 'Long-term Gains', 'Long-term Losses', 
                          'Total Transactions', 'Short-term Transactions', 'Long-term Transactions'],
                'Value': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
            })
        
        df = pd.DataFrame([
            {
                'gain_loss': gain.gain_loss,
                'is_short_term': gain.is_short_term
            }
            for gain in capital_gains
        ])
        
        total_gains = df[df['gain_loss'] > 0]['gain_loss'].sum()
        total_losses = abs(df[df['gain_loss'] < 0]['gain_loss'].sum())
        net_gain = total_gains - total_losses
        
        short_term_df = df[df['is_short_term']]
        long_term_df = df[~df['is_short_term']]
        
        short_term_gains = short_term_df[short_term_df['gain_loss'] > 0]['gain_loss'].sum()
        short_term_losses = abs(short_term_df[short_term_df['gain_loss'] < 0]['gain_loss'].sum())
        long_term_gains = long_term_df[long_term_df['gain_loss'] > 0]['gain_loss'].sum()
        long_term_losses = abs(long_term_df[long_term_df['gain_loss'] < 0]['gain_loss'].sum())
        
        summary_data = [
            ['Total Gains', f"${total_gains:,.2f}"],
            ['Total Losses', f"${total_losses:,.2f}"],
            ['Net Gain', f"${net_gain:,.2f}"],
            ['Short-term Gains', f"${short_term_gains:,.2f}"],
            ['Short-term Losses', f"${short_term_losses:,.2f}"],
            ['Long-term Gains', f"${long_term_gains:,.2f}"],
            ['Long-term Losses', f"${long_term_losses:,.2f}"],
            ['Total Transactions', len(df)],
            ['Short-term Transactions', len(short_term_df)],
            ['Long-term Transactions', len(long_term_df)]
        ]
        
        return pd.DataFrame(summary_data, columns=['Metric', 'Value'])
    
    def _create_yearly_dataframe(self, capital_gains: List[CapitalGain]) -> pd.DataFrame:
        """Create yearly breakdown DataFrame."""
        if not capital_gains:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {
                'year': gain.sell_date.year,
                'gain_loss': gain.gain_loss,
                'is_short_term': gain.is_short_term,
                'symbol': gain.symbol
            }
            for gain in capital_gains
        ])
        
        yearly_data = []
        for year in sorted(df['year'].unique()):
            year_data = df[df['year'] == year]
            
            total_gains = year_data[year_data['gain_loss'] > 0]['gain_loss'].sum()
            total_losses = abs(year_data[year_data['gain_loss'] < 0]['gain_loss'].sum())
            net_gain = total_gains - total_losses
            
            short_term_data = year_data[year_data['is_short_term']]
            long_term_data = year_data[~year_data['is_short_term']]
            
            yearly_data.append({
                'Year': year,
                'Total_Gains': f"${total_gains:,.2f}",
                'Total_Losses': f"${total_losses:,.2f}",
                'Net_Gain': f"${net_gain:,.2f}",
                'Short_term_Gains': f"${short_term_data[short_term_data['gain_loss'] > 0]['gain_loss'].sum():,.2f}",
                'Short_term_Losses': f"${abs(short_term_data[short_term_data['gain_loss'] < 0]['gain_loss'].sum()):,.2f}",
                'Long_term_Gains': f"${long_term_data[long_term_data['gain_loss'] > 0]['gain_loss'].sum():,.2f}",
                'Long_term_Losses': f"${abs(long_term_data[long_term_data['gain_loss'] < 0]['gain_loss'].sum()):,.2f}",
                'Transaction_Count': len(year_data),
                'Symbols_Traded': year_data['symbol'].nunique()
            })
        
        return pd.DataFrame(yearly_data)
    
    def export_transaction_summary(self, 
                                 transactions_df: pd.DataFrame, 
                                 filename: str = None) -> str:
        """
        Export transaction summary to Excel file.
        
        Args:
            transactions_df (pd.DataFrame): Transaction DataFrame
            filename (str): Optional custom filename
            
        Returns:
            str: Path to the exported Excel file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"transaction_summary_{timestamp}.xlsx"
        
        filepath = os.path.join(self.output_dir, filename)
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Export all transactions
            transactions_df.to_excel(writer, sheet_name='All_Transactions', index=False)
            
            # Export buy transactions
            buy_df = transactions_df[transactions_df['Type'] == 'BUY']
            if not buy_df.empty:
                buy_df.to_excel(writer, sheet_name='Buy_Transactions', index=False)
            
            # Export sell transactions
            sell_df = transactions_df[transactions_df['Type'] == 'SELL']
            if not sell_df.empty:
                sell_df.to_excel(writer, sheet_name='Sell_Transactions', index=False)
            
            # Export summary by symbol
            symbol_summary = transactions_df.groupby('Symbol').agg({
                'Quantity': 'sum',
                'Total_Value': 'sum',
                'Fees': 'sum',
                'Type': 'count'
            }).rename(columns={'Type': 'Transaction_Count'})
            symbol_summary.to_excel(writer, sheet_name='Symbol_Summary')
        
        return filepath

    def export_mutual_fund_ledger(
        self,
        trades_df: pd.DataFrame,
        dividends_df: pd.DataFrame,
        filename: str = None,
    ) -> str:
        """Export mutual fund purchases/redemptions and dividends to one workbook."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"mutual_fund_ledger_{timestamp}.xlsx"

        filepath = os.path.join(self.output_dir, filename)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            if trades_df is not None and not trades_df.empty:
                trades_df.to_excel(writer, sheet_name="MF_Trades", index=False)
            else:
                pd.DataFrame(
                    columns=[
                        "Txn_Date",
                        "Symbol",
                        "ISIN_Name",
                        "Type",
                        "Quantity",
                        "Price",
                        "Amount",
                        "Fees",
                        "Total_Value",
                    ]
                ).to_excel(writer, sheet_name="MF_Trades", index=False)

            if dividends_df is not None and not dividends_df.empty:
                dividends_df.to_excel(writer, sheet_name="Dividends", index=False)
            else:
                pd.DataFrame(
                    columns=["Date", "Fund_Name", "ISIN", "Amount", "Notes"]
                ).to_excel(writer, sheet_name="Dividends", index=False)

        return filepath

    def export_fixed_income_ledger(
        self,
        trades_df: pd.DataFrame,
        interest_df: pd.DataFrame,
        filename: str = None,
    ) -> str:
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fixed_income_ledger_{timestamp}.xlsx"

        filepath = os.path.join(self.output_dir, filename)

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            if trades_df is not None and not trades_df.empty:
                trades_df.to_excel(writer, sheet_name="FI_Trades", index=False)
            else:
                pd.DataFrame(
                    columns=[
                        "Txn_Date",
                        "Symbol",
                        "ISIN_Name",
                        "Type",
                        "Quantity",
                        "Price",
                        "Amount",
                        "Fees",
                        "Total_Value",
                    ]
                ).to_excel(writer, sheet_name="FI_Trades", index=False)

            if interest_df is not None and not interest_df.empty:
                interest_df.to_excel(writer, sheet_name="Interest", index=False)
            else:
                pd.DataFrame(
                    columns=["Date", "Fund_Name", "ISIN", "Amount", "Notes"]
                ).to_excel(writer, sheet_name="Interest", index=False)

        return filepath

