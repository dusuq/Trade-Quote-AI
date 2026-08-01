import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/constants/app_constants.dart';
import 'package:tradequote_mobile/core/sync/offline_repositories.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/pricebook/domain/pricebook_item.dart';

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
    final itemsAsync = ref.watch(offlinePricebookProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Trade Pricebook'),
        actions: [
          IconButton(
            icon: const Icon(LucideIcons.refreshCw),
            onPressed: () => ref.invalidate(offlinePricebookProvider),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppColors.accent,
          labelColor: AppColors.accent,
          unselectedLabelColor: AppColors.textSecondary,
          tabs: const [
            Tab(text: 'All Items'),
            Tab(text: 'Material'),
            Tab(text: 'Labor'),
            Tab(text: 'Equipment'),
          ],
        ),
      ),
      body: Column(
        children: [
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
          Expanded(
            child: itemsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(LucideIcons.alertTriangle,
                        size: 48, color: AppColors.error),
                    const SizedBox(height: 12),
                    const Text(
                      'Failed to load pricebook',
                      style: TextStyle(
                          fontSize: 16, color: AppColors.textPrimary),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      error.toString(),
                      style: const TextStyle(
                          fontSize: 13, color: AppColors.textMuted),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    ElevatedButton.icon(
                      icon: const Icon(LucideIcons.refreshCw, size: 16),
                      label: const Text('Retry'),
                      onPressed: () => ref.invalidate(offlinePricebookProvider),
                    ),
                  ],
                ),
              ),
              data: (allItems) => TabBarView(
                controller: _tabController,
                children: [
                  _buildItemList(allItems, null),
                  _buildItemList(allItems, 'material'),
                  _buildItemList(allItems, 'labor'),
                  _buildItemList(allItems, 'equipment'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildItemList(List<PricebookItem> items, String? kindFilter) {
    final filtered = items.where((item) {
      final matchesKind = kindFilter == null || item.kind == kindFilter;
      final matchesQuery = _searchQuery.isEmpty ||
          item.name.toLowerCase().contains(_searchQuery.toLowerCase()) ||
          (item.sku != null &&
              item.sku!.toLowerCase().contains(_searchQuery.toLowerCase()));
      return matchesKind && matchesQuery;
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
        bg = AppColors.primary.withValues(alpha: 0.2);
        border = AppColors.primaryLight;
        break;
      case 'labor':
        bg = AppColors.accent.withValues(alpha: 0.2);
        border = AppColors.accent;
        break;
      case 'equipment':
        bg = AppColors.info.withValues(alpha: 0.2);
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
