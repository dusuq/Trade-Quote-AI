import 'package:tradequote_mobile/features/quotes/domain/quote_models.dart';

class QuoteCalculationResult {
  final int subtotalMinor; // Sum of non-optional line items
  final int taxMinor; // subtotalMinor * taxRateBps / 10000
  final int totalMinor; // subtotalMinor + taxMinor
  final int optionalSubtotalMinor; // Sum of optional line items

  QuoteCalculationResult({
    required this.subtotalMinor,
    required this.taxMinor,
    required this.totalMinor,
    required this.optionalSubtotalMinor,
  });
}

class QuoteCalculator {
  static QuoteCalculationResult calculate({
    required List<QuoteLineItem> lineItems,
    required int taxRateBps,
  }) {
    int subtotal = 0;
    int optionalSubtotal = 0;

    for (final item in lineItems) {
      if (item.isOptional) {
        optionalSubtotal += item.lineTotalMinor;
      } else {
        subtotal += item.lineTotalMinor;
      }
    }

    final double taxMult = taxRateBps / 10000.0;
    final int tax = (subtotal * taxMult).round();
    final int total = subtotal + tax;

    return QuoteCalculationResult(
      subtotalMinor: subtotal,
      taxMinor: tax,
      totalMinor: total,
      optionalSubtotalMinor: optionalSubtotal,
    );
  }
}
