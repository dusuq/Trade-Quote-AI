class QuoteLineItem {
  final String id;
  final String? pricebookItemId;
  final String kind;
  final String description;
  final double quantity;
  final String unit;
  final int unitCostMinor;
  final int markupBps;
  final bool isOptional;
  final int sortOrder;

  QuoteLineItem({
    required this.id,
    this.pricebookItemId,
    required this.kind,
    required this.description,
    this.quantity = 1.0,
    this.unit = 'each',
    this.unitCostMinor = 0,
    this.markupBps = 0,
    this.isOptional = false,
    this.sortOrder = 0,
  });

  // Calculate unit price in cents: unit_cost_minor * (1 + markup_bps / 10000)
  int get unitPriceMinor {
    final double markupMult = 1.0 + (markupBps / 10000.0);
    return (unitCostMinor * markupMult).round();
  }

  // Calculate line total in cents: unitPriceMinor * quantity
  int get lineTotalMinor {
    return (unitPriceMinor * quantity).round();
  }

  QuoteLineItem copyWith({
    String? description,
    double? quantity,
    int? unitCostMinor,
    int? markupBps,
    bool? isOptional,
  }) {
    return QuoteLineItem(
      id: id,
      pricebookItemId: pricebookItemId,
      kind: kind,
      description: description ?? this.description,
      quantity: quantity ?? this.quantity,
      unit: unit,
      unitCostMinor: unitCostMinor ?? this.unitCostMinor,
      markupBps: markupBps ?? this.markupBps,
      isOptional: isOptional ?? this.isOptional,
      sortOrder: sortOrder,
    );
  }
}

class Quote {
  final String id;
  final String tenantId;
  final String customerId;
  final String customerName;
  final String number;
  final String title;
  final String status; // draft, sent, accepted, rejected
  final int taxRateBps;
  final int currentVersion;
  final DateTime createdAt;
  final List<QuoteLineItem> lineItems;

  Quote({
    required this.id,
    required this.tenantId,
    required this.customerId,
    required this.customerName,
    required this.number,
    required this.title,
    required this.status,
    required this.taxRateBps,
    required this.currentVersion,
    required this.createdAt,
    required this.lineItems,
  });
}
