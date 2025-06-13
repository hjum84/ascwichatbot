from database_monitor import get_database_size

stats = get_database_size()
breakdown = stats.get('db_breakdown', {})

print('=== CORRECTED BREAKDOWN ===')
print('Storage Bar (% of 1GB total):')
for name, data in breakdown.items():
    pct_total = data.get('percentage_of_total_capacity', 0)
    print(f'  {name}: {pct_total:.3f}%')

print('\nBreakdown Cards (% of 16MB used):')
for name, data in breakdown.items():
    pct_used = data.get('percentage', 0)
    print(f'  {name}: {pct_used:.2f}%')

print(f'\nTotal used: {stats.get("total_size", "N/A")}')
print(f'Max capacity: {stats.get("max_size_pretty", "N/A")}') 