import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';

final mockCustomersProvider = Provider<List<Customer>>((ref) {
  return [
    Customer(
      id: 'cust-101',
      tenantId: '11111111-1111-1111-1111-111111111111',
      name: 'Johnathan Miller',
      companyName: 'Miller Residential Properties',
      phone: '(555) 234-5678',
      email: 'j.miller@example.com',
      status: 'active',
      tags: ['VIP', 'HVAC Upgrade', 'Commercial'],
      properties: [
        CustomerProperty(
          id: 'prop-1',
          addressLine1: '742 Evergreen Terrace',
          city: 'Springfield',
          state: 'IL',
          zipCode: '62704',
          propertyType: 'Single Family',
        ),
      ],
      contacts: [
        CustomerContact(
          id: 'con-1',
          name: 'Johnathan Miller',
          email: 'j.miller@example.com',
          phone: '(555) 234-5678',
          role: 'Property Owner',
        ),
      ],
    ),
    Customer(
      id: 'cust-102',
      tenantId: '11111111-1111-1111-1111-111111111111',
      name: 'Sarah Jenkins',
      companyName: 'Jenkins Dental Clinic',
      phone: '(555) 876-5432',
      email: 's.jenkins@example.com',
      status: 'active',
      tags: ['Electrical Panel', 'Urgent'],
      properties: [
        CustomerProperty(
          id: 'prop-2',
          addressLine1: '1200 Market Street, Suite 400',
          city: 'Chicago',
          state: 'IL',
          zipCode: '60601',
          propertyType: 'Commercial Suite',
        ),
      ],
      contacts: [
        CustomerContact(
          id: 'con-2',
          name: 'Sarah Jenkins',
          email: 's.jenkins@example.com',
          phone: '(555) 876-5432',
          role: 'Clinic Manager',
        ),
      ],
    ),
    Customer(
      id: 'cust-103',
      tenantId: '11111111-1111-1111-1111-111111111111',
      name: 'Robert Davis',
      companyName: 'Davis Plumbing Maintenance',
      phone: '(555) 345-6789',
      email: 'r.davis@example.com',
      status: 'prospect',
      tags: ['Plumbing', 'Water Heater'],
      properties: [
        CustomerProperty(
          id: 'prop-3',
          addressLine1: '450 Oak Ridge Lane',
          city: 'Naperville',
          state: 'IL',
          zipCode: '60540',
          propertyType: 'Residential',
        ),
      ],
      contacts: [],
    ),
  ];
});

class CustomerListScreen extends ConsumerStatefulWidget {
  const CustomerListScreen({super.key});

  @override
  ConsumerState<CustomerListScreen> createState() => _CustomerListScreenState();
}

class _CustomerListScreenState extends ConsumerState<CustomerListScreen> {
  String _searchQuery = '';

  @override
  Widget build(BuildContext context) {
    final customers = ref.watch(mockCustomersProvider);
    final filtered = customers.where((c) {
      final query = _searchQuery.toLowerCase();
      return c.name.toLowerCase().contains(query) ||
          c.companyName.toLowerCase().contains(query) ||
          c.tags.any((t) => t.toLowerCase().contains(query));
    }).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Customer CRM'),
        actions: [
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
          // Search Bar
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
          // Customer List
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              itemCount: filtered.length,
              itemBuilder: (context, index) {
                final customer = filtered[index];
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
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: AppColors.primary.withOpacity(0.2),
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
                        // Tags
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: customer.tags.map((tag) {
                            return Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
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
                        // Property
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
                        // Actions
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
              },
            ),
          ),
        ],
      ),
    );
  }
}
