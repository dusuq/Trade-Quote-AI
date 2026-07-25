import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/constants/app_constants.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/pricebook/domain/pricebook_item.dart';

final mockPricebookItemsProvider = Provider<List<PricebookItem>>((ref) {
  return [
    // Electrical
    PricebookItem(
      id: 'item-ele-1',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'material',
      sku: 'ELE-PNL-200A',
      name: '200A Main Breaker Panel (30-Space)',
      description: 'Indoor NEMA 1 main breaker load center panel',
      unit: 'each',
      unitCostMinor: 18500, // $185.00
      defaultMarkupBps: 4000, // 40% markup
      currency: 'USD',
      trade: 'electrical',
    ),
    PricebookItem(
      id: 'item-ele-2',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'material',
      sku: 'ELE-WIR-122-250',
      name: '12/2 NMB Romex Wire (250ft Roll)',
      description: '12 AWG 2-conductor copper wire with ground',
      unit: 'roll',
      unitCostMinor: 11200, // $112.00
      defaultMarkupBps: 3500, // 35% markup
      currency: 'USD',
      trade: 'electrical',
    ),
    PricebookItem(
      id: 'item-ele-3',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'labor',
      sku: 'ELE-LBR-MSTR',
      name: 'Master Electrician Hourly Rate',
      description: 'Licensed master electrician labor rate',
      unit: 'hour',
      unitCostMinor: 13500, // $135.00
      defaultMarkupBps: 2500, // 25% markup
      currency: 'USD',
      trade: 'electrical',
    ),
    // Plumbing
    PricebookItem(
      id: 'item-plm-1',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'material',
      sku: 'PLM-WHT-TNKL-50',
      name: '50-Gal Tankless Gas Water Heater',
      description: 'Condensing high-efficiency natural gas unit',
      unit: 'each',
      unitCostMinor: 145000, // $1,450.00
      defaultMarkupBps: 3000, // 30% markup
      currency: 'USD',
      trade: 'plumbing',
    ),
    PricebookItem(
      id: 'item-plm-2',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'labor',
      sku: 'PLM-LBR-MSTR',
      name: 'Master Plumber Hourly Rate',
      description: 'Licensed master plumber labor rate',
      unit: 'hour',
      unitCostMinor: 14000, // $140.00
      defaultMarkupBps: 2500, // 25% markup
      currency: 'USD',
      trade: 'plumbing',
    ),
    // HVAC
    PricebookItem(
      id: 'item-hvc-1',
      tenantId: '11111111-1111-1111-1111-111111111111',
      kind: 'material',
      sku: 'HVC-CND-3T-16S',
      name: '3-Ton 16 SEER2 Heat Pump Condenser',
      description: 'Outdoor split system heat pump unit',
      unit: 'each',
      unitCostMinor: 245000, // $2,450.00
      defaultMarkupBps: 3000, // 30% markup
      currency: 'USD',
      trade: 'hvac',
    ),
  ];
});

class PricebookScreen extends ConsumerStatefulWidget {
  const PricebookScreen({super.key});

  @override
  ConsumerState<PricebookScreen> createState() => _PricebookScreenState();
}

class _PricebookScreenState extends ConsumerState<PricebookScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final allItems = ref.watch(mockPricebookItemsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Trade Pricebook'),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppColors.accent,
          labelColor: AppColors.accent,
          unselectedLabelColor: AppColors.textSecondary,
          tabs: const [
            Tab(text: 'All Items'),
            Tab(text: 'Electrical'),
            Tab(text: 'Plumbing'),
            Tab(text: 'HVAC'),
          ],
        ),
      ),
      body: Column(
        children: [
          // Search Bar
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: TextField(
              decoration: const InputDecoration(
                hintText: 'Search catalog by SKU, name, or description...',
                prefixIcon: Icon(LucideIcons.search, color: AppColors.textMuted),
              ),
              onChanged: (val) => setState(() => _searchQuery = val),
            ),
          ),
          // Tab View
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                _buildItemList(allItems, null),
                _buildItemList(allItems, 'electrical'),
                _buildItemList(allItems, 'plumbing'),
                _buildItemList(allItems, 'hvac'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildItemList(List<PricebookItem> items, String? tradeFilter) {
    final filtered = items.where((item) {
      final matchesTrade = tradeFilter == null || item.trade == tradeFilter;
      final matchesQuery = _searchQuery.isEmpty ||
          item.name.toLowerCase().contains(_searchQuery.toLowerCase()) ||
          (item.sku != null &&
              item.sku!.toLowerCase().contains(_searchQuery.toLowerCase()));
      return matchesTrade && matchesQuery;
    }).toList();

    if (filtered.isEmpty) {
      return const Center(
        child: Text('No catalog items found',
            style: TextStyle(color: AppColors.textMuted)),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16.0),
      itemCount: filtered.length,
      itemBuilder: (context, index) {
        final item = filtered[index];
        return Card(
          margin: const EdgeInsets.only(bottom: 12.0),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        item.name,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: AppColors.textPrimary,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    _buildKindBadge(item.kind),
                  ],
                ),
                if (item.sku != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    'SKU: ${item.sku}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: AppColors.accent,
                    ),
                  ),
                ],
                if (item.description != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    item.description!,
                    style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
                const Divider(height: 20, color: AppColors.border),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Cost: ${AppConstants.formatCurrency(item.unitCostMinor)} / ${item.unit}',
                          style: const TextStyle(
                              fontSize: 13, color: AppColors.textMuted),
                        ),
                        Text(
                          'Markup: ${AppConstants.formatBps(item.defaultMarkupBps)}',
                          style: const TextStyle(
                              fontSize: 13, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        const Text('Unit Price',
                            style: TextStyle(
                                fontSize: 11, color: AppColors.textMuted)),
                        Text(
                          AppConstants.formatCurrency(item.unitPriceMinor),
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: AppColors.success,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildKindBadge(String kind) {
    Color bg;
    Color border;
    switch (kind.toLowerCase()) {
      case 'material':
        bg = AppColors.primary.withOpacity(0.2);
        border = AppColors.primaryLight;
        break;
      case 'labor':
        bg = AppColors.accent.withOpacity(0.2);
        border = AppColors.accent;
        break;
      case 'equipment':
        bg = AppColors.info.withOpacity(0.2);
        border = AppColors.info;
        break;
      default:
        bg = AppColors.surfaceLight;
        border = AppColors.border;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: Text(
        kind.toUpperCase(),
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.bold,
          color: border,
        ),
      ),
    );
  }
}
