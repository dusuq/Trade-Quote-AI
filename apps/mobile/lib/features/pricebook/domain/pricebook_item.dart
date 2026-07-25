class PricebookItem {
  final String id;
  final String tenantId;
  final String kind; // material, labor, equipment
  final String? sku;
  final String name;
  final String? description;
  final String unit;
  final int unitCostMinor;
  final int defaultMarkupBps;
  final String currency;
  final String trade; // electrical, plumbing, hvac

  PricebookItem({
    required this.id,
    required this.tenantId,
    required this.kind,
    this.sku,
    required this.name,
    this.description,
    required this.unit,
    required this.unitCostMinor,
    required this.defaultMarkupBps,
    required this.currency,
    required this.trade,
  });

  // Calculate unit price from cost + default markup bps
  int get unitPriceMinor {
    final double markupMult = 1.0 + (defaultMarkupBps / 10000.0);
    return (unitCostMinor * markupMult).round();
  }
}
