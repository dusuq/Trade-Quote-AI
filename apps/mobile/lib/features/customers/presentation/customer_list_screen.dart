import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/sync/offline_repositories.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';

class CustomerListScreen extends ConsumerStatefulWidget {
  const CustomerListScreen({super.key});

  @override
  ConsumerState<CustomerListScreen> createState() => _CustomerListScreenState();
}

class _CustomerListScreenState extends ConsumerState<CustomerListScreen> {
  String _searchQuery = '';

  @override
  Widget build(BuildContext context) {
    final customersAsync = ref.watch(offlineCustomersProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Customer CRM'),
        actions: [
          IconButton(
            icon: const Icon(LucideIcons.refreshCw),
            onPressed: () => ref.invalidate(offlineCustomersProvider),
          ),
          IconButton(
            icon: const Icon(LucideIcons.userPlus),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('New Customer Form Ready')),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: TextField(
              decoration: const InputDecoration(
                hintText: 'Search customers, properties, or tags...',
                prefixIcon: Icon(LucideIcons.search, color: AppColors.textMuted),
              ),
              onChanged: (val) => setState(() => _searchQuery = val),
            ),
          ),
          Expanded(
            child: customersAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(LucideIcons.alertTriangle,
                        size: 48, color: AppColors.error),
                    const SizedBox(height: 12),
                    const Text(
                      'Failed to load customers',
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
                      onPressed: () => ref.invalidate(offlineCustomersProvider),
                    ),
                  ],
                ),
              ),
              data: (customers) {
                final filtered = customers.where((c) {
                  final query = _searchQuery.toLowerCase();
                  return query.isEmpty ||
                      c.name.toLowerCase().contains(query) ||
                      c.companyName.toLowerCase().contains(query) ||
                      c.tags.any((t) => t.toLowerCase().contains(query));
                }).toList();

                if (filtered.isEmpty) {
                  return Center(
                    child: Text(
                      _searchQuery.isEmpty
                          ? 'No customers yet'
                          : 'No matching customers',
                      style: const TextStyle(color: AppColors.textMuted),
                    ),
                  );
                }

                return ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final customer = filtered[index];
                    return _buildCustomerCard(customer);
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCustomerCard(Customer customer) {
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
                Text(
                  customer.name,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppColors.primaryLight),
                  ),
                  child: Text(
                    customer.status.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: AppColors.primaryLight,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              customer.companyName,
              style: const TextStyle(
                fontSize: 14,
                color: AppColors.textSecondary,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: customer.tags.map((tag) {
                return Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLight,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '#$tag',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.accent,
                    ),
                  ),
                );
              }).toList(),
            ),
            const Divider(height: 24, color: AppColors.border),
            if (customer.properties.isNotEmpty)
              Row(
                children: [
                  const Icon(LucideIcons.mapPin,
                      size: 16, color: AppColors.textMuted),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      '${customer.properties.first.addressLine1}, ${customer.properties.first.city}',
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppColors.textSecondary,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.textPrimary,
                      side: const BorderSide(color: AppColors.border),
                    ),
                    icon: const Icon(LucideIcons.phone, size: 16),
                    label: const Text('Call'),
                    onPressed: () {},
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(LucideIcons.filePlus, size: 16),
                    label: const Text('Create Quote'),
                    onPressed: () {
                      context.push('/quotes/new', extra: customer);
                    },
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
