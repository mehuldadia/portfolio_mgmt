"""
Script to create sample stock transaction data for testing.
"""

import pandas as pd
from datetime import datetime, timedelta
import random
import os

def create_sample_data():
    """Create sample stock transaction data."""
    
    # Sample stock symbols
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX']
    
    # Generate sample transactions
    transactions = []
    start_date = datetime(2022, 1, 1)
    
    for symbol in symbols:
        # Generate 3-5 transactions per symbol
        num_transactions = random.randint(3, 5)
        current_date = start_date
        shares_held = 0
        
        for i in range(num_transactions):
            # Random date within the year
            days_offset = random.randint(0, 300)
            transaction_date = start_date + timedelta(days=days_offset)
            
            # Random price (realistic range)
            base_price = random.uniform(50, 500)
            price = round(base_price, 2)
            
            # Random quantity
            quantity = random.randint(10, 100)
            
            # Determine if buy or sell
            if shares_held == 0 or random.random() < 0.6:  # 60% chance to buy
                transaction_type = 'BUY'
                shares_held += quantity
            else:
                transaction_type = 'SELL'
                # Don't sell more than we have
                quantity = min(quantity, shares_held)
                shares_held -= quantity
            
            # Random fees
            fees = round(random.uniform(5, 15), 2)
            
            transactions.append({
                'Date': transaction_date.strftime('%Y-%m-%d'),
                'Type': transaction_type,
                'Symbol': symbol,
                'Quantity': quantity,
                'Price': price,
                'Fees': fees
            })
    
    # Create DataFrame and save to Excel
    df = pd.DataFrame(transactions)
    df = df.sort_values('Date').reset_index(drop=True)
    
    # Save to Excel file
    os.makedirs('data', exist_ok=True)
    filepath = 'data/sample_transactions.xlsx'
    df.to_excel(filepath, index=False)
    
    print(f"Sample data created: {filepath}")
    print(f"Total transactions: {len(df)}")
    print(f"Symbols: {df['Symbol'].nunique()}")
    print(f"Date range: {df['Date'].min()} to {df['Date'].max()}")
    
    return filepath

if __name__ == "__main__":
    create_sample_data()





