"""
Test script to verify the complete stock gains analyzer system.
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.transaction_reader import TransactionReader
from modules.gains_calculator import GainsCalculator
from modules.excel_exporter import ExcelExporter
from sample_data import create_sample_data

def test_system():
    """Test the complete system with sample data."""
    print("=" * 60)
    print("STOCK GAINS ANALYZER - SYSTEM TEST")
    print("=" * 60)
    
    # Step 1: Create sample data
    print("\n1. Creating sample transaction data...")
    sample_file = create_sample_data()
    print(f"✓ Sample data created: {sample_file}")
    
    # Step 2: Read transactions
    print("\n2. Reading transactions...")
    reader = TransactionReader()
    try:
        transactions_df = reader.read_transactions(sample_file)
        print(f"✓ Successfully read {len(transactions_df)} transactions")
        
        # Show transaction summary
        summary = reader.get_transaction_summary(transactions_df)
        print(f"  - Date range: {summary['date_range']['start']} to {summary['date_range']['end']}")
        print(f"  - Symbols: {summary['symbols']} ({', '.join(summary['unique_symbols'])})")
        print(f"  - Buy transactions: {summary['transaction_types']['BUY']}")
        print(f"  - Sell transactions: {summary['transaction_types']['SELL']}")
        
    except Exception as e:
        print(f"✗ Error reading transactions: {e}")
        return False
    
    # Step 3: Calculate gains
    print("\n3. Calculating capital gains...")
    calculator = GainsCalculator()
    try:
        capital_gains, remaining_positions = calculator.calculate_gains(transactions_df)
        print(f"✓ Calculated {len(capital_gains)} capital gain transactions")
        print(f"✓ {len(remaining_positions)} remaining positions")
        
        # Show gains summary
        gains_summary = calculator.get_gains_summary(capital_gains)
        print(f"  - Net gain: ${gains_summary['net_gain']:.2f}")
        print(f"  - Total gains: ${gains_summary['total_gains']:.2f}")
        print(f"  - Total losses: ${gains_summary['total_losses']:.2f}")
        print(f"  - Short-term transactions: {gains_summary['short_term_transactions']}")
        print(f"  - Long-term transactions: {gains_summary['long_term_transactions']}")
        
    except Exception as e:
        print(f"✗ Error calculating gains: {e}")
        return False
    
    # Step 4: Export to Excel
    print("\n4. Exporting to Excel...")
    exporter = ExcelExporter()
    try:
        excel_file = exporter.export_capital_gains(capital_gains, remaining_positions)
        print(f"✓ Capital gains exported to: {excel_file}")
        
        # Also export transaction summary
        transaction_file = exporter.export_transaction_summary(transactions_df)
        print(f"✓ Transaction summary exported to: {transaction_file}")
        
    except Exception as e:
        print(f"✗ Error exporting to Excel: {e}")
        return False
    
    # Step 5: Show detailed results
    print("\n5. Detailed Results:")
    print("-" * 40)
    
    if capital_gains:
        print("\nTop 5 Capital Gains:")
        sorted_gains = sorted(capital_gains, key=lambda x: x.gain_loss, reverse=True)
        for i, gain in enumerate(sorted_gains[:5]):
            print(f"  {i+1}. {gain.symbol}: ${gain.gain_loss:.2f} "
                  f"({'Short-term' if gain.is_short_term else 'Long-term'})")
    
    if remaining_positions:
        print(f"\nRemaining Positions ({len(remaining_positions)}):")
        for position in remaining_positions[:5]:  # Show first 5
            print(f"  - {position.symbol}: {position.quantity} shares @ ${position.price:.2f}")
        if len(remaining_positions) > 5:
            print(f"  ... and {len(remaining_positions) - 5} more")
    
    # Step 6: Yearly breakdown
    print("\n6. Yearly Breakdown:")
    yearly_summary = calculator.get_yearly_summary(capital_gains)
    for year, data in sorted(yearly_summary.items()):
        print(f"  {year}: Net ${data['net_gain']:.2f} "
              f"({data['transaction_count']} transactions, {data['symbols_traded']} symbols)")
    
    print("\n" + "=" * 60)
    print("SYSTEM TEST COMPLETED SUCCESSFULLY! ✓")
    print("=" * 60)
    print("\nTo run the web application:")
    print("  python app.py")
    print("\nThen open your browser to: http://localhost:5000")
    
    return True

if __name__ == "__main__":
    success = test_system()
    if not success:
        sys.exit(1)





