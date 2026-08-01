import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:lucide_icons/lucide_icons.dart';
import 'package:tradequote_mobile/core/constants/app_constants.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';
import 'package:tradequote_mobile/features/quotes/application/quote_calculator.dart';
import 'package:tradequote_mobile/features/quotes/domain/quote_models.dart';

class QuoteBuilderScreen extends ConsumerStatefulWidget {
  final Customer? customer;

  const QuoteBuilderScreen({super.key, this.customer});

  @override
  ConsumerState<QuoteBuilderScreen> createState() => _QuoteBuilderScreenState();
}

class _QuoteBuilderScreenState extends ConsumerState<QuoteBuilderScreen> {
  late String _title;
  final int _taxRateBps = 875; // 8.75% default tax
  int _currentVersion = 1;
  String _status = 'DRAFT';

  final List<QuoteLineItem> _items = [
    QuoteLineItem(
      id: 'li-1',
      kind: 'material',
      description: '200A Main Breaker Load Center Panel',
      quantity: 1,
      unit: 'each',
      unitCostMinor: 18500, // $185.00
      markupBps: 4000, // 40% -> $259.00
    ),
    QuoteLineItem(
      id: 'li-2',
      kind: 'material',
      description: '12/2 NMB Romex Wire (250ft Roll)',
      quantity: 2,
      unit: 'roll',
      unitCostMinor: 11200, // $112.00
      markupBps: 3500, // 35% -> $151.20 * 2 = $302.40
    ),
    QuoteLineItem(
      id: 'li-3',
      kind: 'labor',
      description: 'Master Electrician Service & Panel Upgrade Labor',
      quantity: 6,
      unit: 'hour',
      unitCostMinor: 13500, // $135.00
      markupBps: 2500, // 25% -> $168.75 * 6 = $1012.50
    ),
    QuoteLineItem(
      id: 'li-4',
      kind: 'material',
      description: 'Whole House Surge Protection Device (Optional)',
      quantity: 1,
      unit: 'each',
      unitCostMinor: 9500,
      markupBps: 3500,
      isOptional: true,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _title = widget.customer != null
        ? 'Service Estimate — ${widget.customer!.name}'
        : 'New Field Estimate';
  }

  void _addItem() {
    setState(() {
      _items.add(QuoteLineItem(
        id: 'li-${DateTime.now().millisecondsSinceEpoch}',
        kind: 'material',
        description: 'New Field Item',
        quantity: 1,
        unitCostMinor: 5000,
        markupBps: 3000,
      ));
    });
  }

  void _removeItem(int index) {
    setState(() {
      _items.removeAt(index);
    });
  }

  @override
  Widget build(BuildContext context) {
    final calc = QuoteCalculator.calculate(
      lineItems: _items,
      taxRateBps: _taxRateBps,
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          Container(
            margin: const EdgeInsets.only(right: 16),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.accent),
            ),
            child: Center(
              child: Text(
                'v$_currentVersion · $_status',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: AppColors.accent,
                ),
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Customer Banner
            if (widget.customer != null)
              Card(
                margin: const EdgeInsets.only(bottom: 16),
                color: AppColors.surfaceLight,
                child: Padding(
                  padding: const EdgeInsets.all(14.0),
                  child: Row(
                    children: [
                      const CircleAvatar(
                        backgroundColor: AppColors.primary,
                        child: Icon(LucideIcons.user, color: Colors.white),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.customer!.name,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: AppColors.textPrimary,
                              ),
                            ),
                            Text(
                              widget.customer!.properties.isNotEmpty
                                  ? widget.customer!.properties.first.addressLine1
                                  : widget.customer!.phone,
                              style: const TextStyle(
                                fontSize: 13,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),

            // Section Header
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Estimate Line Items',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
                TextButton.icon(
                  icon: const Icon(LucideIcons.plusCircle, size: 18),
                  label: const Text('Add Item'),
                  onPressed: _addItem,
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Line Items List
            ListView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _items.length,
              itemBuilder: (context, index) {
                final item = _items[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: Padding(
                    padding: const EdgeInsets.all(14.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                initialValue: item.description,
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 15),
                                decoration: const InputDecoration(
                                  isDense: true,
                                  contentPadding: EdgeInsets.symmetric(
                                      horizontal: 8, vertical: 8),
                                ),
                                onChanged: (val) {
                                  _items[index] = item.copyWith(description: val);
                                },
                              ),
                            ),
                            IconButton(
                              icon: const Icon(LucideIcons.trash2,
                                  size: 18, color: AppColors.error),
                              onPressed: () => _removeItem(index),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            // Quantity Controls
                            Row(
                              children: [
                                const Text('Qty: ',
                                    style: TextStyle(color: AppColors.textMuted)),
                                IconButton(
                                  icon: const Icon(LucideIcons.minusSquare,
                                      size: 20),
                                  onPressed: () {
                                    if (item.quantity > 1) {
                                      setState(() {
                                        _items[index] = item.copyWith(
                                            quantity: item.quantity - 1);
                                      });
                                    }
                                  },
                                ),
                                Text(
                                  item.quantity.toInt().toString(),
                                  style: const TextStyle(
                                      fontSize: 16, fontWeight: FontWeight.bold),
                                ),
                                IconButton(
                                  icon: const Icon(LucideIcons.plusSquare,
                                      size: 20),
                                  onPressed: () {
                                    setState(() {
                                      _items[index] = item.copyWith(
                                          quantity: item.quantity + 1);
                                    });
                                  },
                                ),
                              ],
                            ),

                            // Optional Checkbox
                            Row(
                              children: [
                                Checkbox(
                                  value: item.isOptional,
                                  activeColor: AppColors.accent,
                                  onChanged: (val) {
                                    setState(() {
                                      _items[index] = item.copyWith(
                                          isOptional: val ?? false);
                                    });
                                  },
                                ),
                                const Text('Optional',
                                    style: TextStyle(
                                        fontSize: 12,
                                        color: AppColors.textSecondary)),
                              ],
                            ),

                            // Total
                            Text(
                              AppConstants.formatCurrency(item.lineTotalMinor),
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: item.isOptional
                                    ? AppColors.textMuted
                                    : AppColors.textPrimary,
                                decoration: item.isOptional
                                    ? TextDecoration.lineThrough
                                    : null,
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

            const SizedBox(height: 16),

            // Summary Card
            Card(
              color: AppColors.surfaceLight,
              child: Padding(
                padding: const EdgeInsets.all(18.0),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Subtotal',
                            style: TextStyle(color: AppColors.textSecondary)),
                        Text(
                          AppConstants.formatCurrency(calc.subtotalMinor),
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Tax (${AppConstants.formatBps(_taxRateBps)})',
                            style:
                                const TextStyle(color: AppColors.textSecondary)),
                        Text(
                          AppConstants.formatCurrency(calc.taxMinor),
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                    if (calc.optionalSubtotalMinor > 0) ...[
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Optional Add-ons',
                              style: TextStyle(color: AppColors.accent)),
                          Text(
                            AppConstants.formatCurrency(calc.optionalSubtotalMinor),
                            style: const TextStyle(
                              fontSize: 14,
                              color: AppColors.accent,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ],
                    const Divider(height: 24, color: AppColors.border),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Estimated Total',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        Text(
                          AppConstants.formatCurrency(calc.totalMinor),
                          style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: AppColors.success,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 24),

            // Action Buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: AppColors.primaryLight),
                    ),
                    icon: const Icon(LucideIcons.history, size: 18),
                    label: const Text('Save Snapshot'),
                    onPressed: () {
                      setState(() => _currentVersion += 1);
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                            content: Text(
                                'Saved Quote Version Snapshot v$_currentVersion')),
                      );
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(LucideIcons.send, size: 18),
                    label: const Text('Send Estimate'),
                    onPressed: () {
                      setState(() => _status = 'SENT');
                      showDialog(
                        context: context,
                        builder: (context) => AlertDialog(
                          backgroundColor: AppColors.surface,
                          title: const Text('Estimate Sent Successfully!'),
                          content: Text(
                              'Estimate for ${AppConstants.formatCurrency(calc.totalMinor)} has been sent to customer via SMS and Email with live audit trail.'),
                          actions: [
                            TextButton(
                              child: const Text('OK'),
                              onPressed: () {
                                Navigator.pop(context);
                              },
                            ),
                          ],
                        ),
                      );
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
