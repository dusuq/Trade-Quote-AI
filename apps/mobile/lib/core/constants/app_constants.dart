import 'package:intl/intl.dart';

class AppConstants {
  static const String appName = 'TradeQuote AI';
  static const String appTagline = 'Field Contracting & Estimate Engine';

  // Minor units currency formatter ($123.45 from 12345 cents)
  static String formatCurrency(int amountMinor, {String currency = 'USD'}) {
    final double amount = amountMinor / 100.0;
    final NumberFormat format = NumberFormat.currency(symbol: r'$', decimalDigits: 2);
    return format.format(amount);
  }

  // Basis Points formatter (3500 bps -> 35.0%)
  static String formatBps(int bps) {
    final double percentage = bps / 100.0;
    return '${percentage.toStringAsFixed(1)}%';
  }
}
