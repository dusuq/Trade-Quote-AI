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

  factory PricebookItem.fromJson(Map<String, dynamic> json) {
    return PricebookItem(
      id: json['id'] as String,
      tenantId: json['tenant_id'] as String? ?? '',
      kind: json['kind'] as String? ?? 'material',
      sku: json['sku'] as String?,
      name: json['name'] as String,
      description: json['description'] as String?,
      unit: json['unit'] as String? ?? 'each',
      unitCostMinor: json['unit_cost_minor'] as int? ?? 0,
      defaultMarkupBps: json['default_markup_bps'] as int? ?? 0,
      currency: json['currency'] as String? ?? 'USD',
      trade: json['trade'] as String? ?? json['kind'] as String? ?? 'material',
    );
  }
}
