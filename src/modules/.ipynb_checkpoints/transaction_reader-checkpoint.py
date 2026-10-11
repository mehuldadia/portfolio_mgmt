"""
Module for reading stock transactions from Excel files.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
import os


class TransactionReader:
    """Handles reading and parsing stock transaction data from Excel files."""
    
    def __init__(self):
        # New format columns
        self.required_columns = [
            'trx date', 'ISIN Code', 'ISIN Name', 'Dr Cr', 
            'DP Qty', 'Closing price', 'Amt'
        ]
        self.optional_columns = [
            'Sett Id', 'Trx Id', 'Counter BO Id', 'Counter BO Name', 
            'Counter DP Sett Id', 'Last Modi D Time'
        ]
    
    def read_transactions(self, file_path: str) -> pd.DataFrame:
        """
        Read stock transactions from an Excel file.
        
        Args:
            file_path (str): Path to the Excel file
            
        Returns:
            pd.DataFrame: DataFrame containing transaction data with standardized column names
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If required columns are missing
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            
            # Normalize column names (strip whitespace, handle case variations)
            df.columns = df.columns.str.strip()
            
            # Check for required columns (case-insensitive)
            df_columns_lower = [col.lower() for col in df.columns]
            required_columns_lower = [col.lower() for col in self.required_columns]
            
            missing_columns = []
            for req_col in required_columns_lower:
                if req_col not in df_columns_lower:
                    missing_columns.append(req_col)
            
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")
            
            # Map column names to standardized names (case-insensitive, handles spacing variations)
            column_mapping = {}
            for col in df.columns:
                # Normalize: lowercase, strip, and replace multiple spaces with single space
                col_normalized = ' '.join(col.lower().strip().split())
                
                if col_normalized == 'trx date' or col_normalized == 'transaction date':
                    column_mapping[col] = 'Txn_Date'
                elif col_normalized == 'isin code' or col_normalized == 'isin':
                    column_mapping[col] = 'Symbol'
                elif col_normalized == 'Dr Cr' or col_normalized == 'dr cr' or col_normalized == 'debit/credit':
                    column_mapping[col] = 'Type'
                elif col_normalized == 'dp qty' or col_normalized == 'quantity' or col_normalized == 'qty':
                    column_mapping[col] = 'Quantity'
                elif col_normalized == 'closing price' or col_normalized == 'price' or col_normalized == 'close price':
                    column_mapping[col] = 'Price'
                elif col_normalized == 'Amt':
                    column_mapping[col] = 'Amount'
                elif col_normalized == 'isin name':
                    column_mapping[col] = 'ISIN_Name'
                else:
                    # Keep other columns as-is
                    column_mapping[col] = col
            
            df = df.rename(columns=column_mapping)
            
            # Convert Date column to datetime
            print("Date values=",df['Txn_Date'].values.tolist())
            df['Txn_Date'] = pd.to_datetime(df['Txn_Date'], errors='coerce')
            if df['Txn_Date'].isna().any():
                raise ValueError("Invalid date values found in 'txn date' column")
            
            # Convert DR/CR to BUY/SELL
            # DR (Debit) typically means BUY, CR (Credit) typically means SELL
            df['Type'] = df['Type'].str.strip().str.upper()
            df['Type'] = df['Type'].replace({'DR': 'BUY', 'CR': 'SELL', 'DEBIT': 'BUY', 'CREDIT': 'SELL'})
            
            # Validate Type values
            valid_types = ['BUY', 'SELL']
            invalid_types = df[~df['Type'].isin(valid_types)]['Type'].unique()
            if len(invalid_types) > 0:
                raise ValueError(f"Invalid transaction types: {invalid_types}. Must be 'Dr' 'Cr' or 'BUY'/'SELL'")
            
            # Convert numeric columns
            df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
            df['Price'] = pd.to_numeric(df['Price'], errors='coerce')
            # Amount can be negative for Debit transactions, so preserve the sign
            df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
            
            # Check for invalid numeric values
            if df['Quantity'].isna().any():
                raise ValueError("Invalid quantity values found in 'DP Qty' column")
            if df['Price'].isna().any():
                raise ValueError("Invalid price values found in 'Closing price' column")
            # Note: Amount can be negative for Debit transactions, so we don't validate for negative values
            if df['Amount'].isna().any():
                raise ValueError("Invalid amount values found in 'Amt' column")
            
            # Add Fees column (set to 0.0 for now, can be calculated from Amount if needed)
            df['Fees'] = 0.0
            
            # Calculate total value for each transaction (for validation)
            df['Total_Value'] = df['Quantity'] * df['Price']
            
            # Sort by date and symbol
            df = df.sort_values(['Txn_Date', 'Symbol'])
            
            return df
            
        except Exception as e:
            raise ValueError(f"Error reading Excel file: {str(e)}")
    
    def validate_transactions(self, df: pd.DataFrame) -> List[str]:
        """
        Validate transaction data for common issues.
        
        Args:
            df (pd.DataFrame): Transaction DataFrame
            
        Returns:
            List[str]: List of validation warnings
        """
        warnings = []
        
        # Check for negative quantities
        negative_qty = df[df['Quantity'] <= 0]
        if not negative_qty.empty:
            warnings.append(f"Found {len(negative_qty)} transactions with non-positive quantities")
        
        # Check for negative prices
        negative_price = df[df['Price'] <= 0]
        if not negative_price.empty:
            warnings.append(f"Found {len(negative_price)} transactions with non-positive prices")
        
        # Note: Amount can be negative for Debit transactions, so we don't validate for negative amounts
        
        # Check for future dates
        future_dates = df[df['Txn_Date'] > datetime.now()]
        if not future_dates.empty:
            warnings.append(f"Found {len(future_dates)} transactions with future dates")
        
        # Check for duplicate transactions
        duplicates = df.duplicated(subset=['Txn_Date', 'Type', 'Symbol', 'Quantity', 'Price'])
        if duplicates.any():
            warnings.append(f"Found {duplicates.sum()} duplicate transactions")
        
        return warnings
    
    def get_transaction_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get a summary of the transaction data.
        
        Args:
            df (pd.DataFrame): Transaction DataFrame
            
        Returns:
            Dict[str, Any]: Summary statistics
        """
        summary = {
            'total_transactions': len(df),
            'date_range': {
                'start': df['Txn_Date'].min().strftime('%Y-%m-%d'),
                'end': df['Txn_Date'].max().strftime('%Y-%m-%d')
            },
            'symbols': df['Symbol'].nunique(),
            'unique_symbols': sorted(df['Symbol'].unique().tolist()),
            'transaction_types': df['Type'].value_counts().to_dict(),
            'total_buy_value': df[df['Type'] == 'BUY']['Total_Value'].sum(),
            'total_sell_value': df[df['Type'] == 'SELL']['Total_Value'].sum(),
            'total_fees': df['Fees'].sum()
        }
        
        return summary

