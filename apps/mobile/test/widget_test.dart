import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tradequote_mobile/core/constants/app_constants.dart';
import 'package:tradequote_mobile/core/sync/offline_repositories.dart';
import 'package:tradequote_mobile/core/theme/app_theme.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';
import 'package:tradequote_mobile/features/customers/presentation/customer_list_screen.dart';
import 'package:tradequote_mobile/features/quotes/application/quote_calculator.dart';
import 'package:tradequote_mobile/features/quotes/domain/quote_models.dart';

Customer _customer(String name) => Customer(
      id: name,
      tenantId: 't',
      name: name,
      companyName: '$name Co',
      phone: '',
      email: '',
      status: 'active',
      tags: const [],
      properties: const [],
      contacts: const [],
    );

void main() {
  group('AppConstants Helper Tests', () {
    test('formatCurrency formats minor units cents to USD string correctly', () {
      expect(AppConstants.formatCurrency(18500), r'$185.00');
      expect(AppConstants.formatCurrency(123456), r'$1,234.56');
      expect(AppConstants.formatCurrency(0), r'$0.00');
    });

    test('formatBps formats basis points to percentage string correctly', () {
      expect(AppConstants.formatBps(3500), '35.0%');
      expect(AppConstants.formatBps(875), '8.8%');
      expect(AppConstants.formatBps(0), '0.0%');
    });
  });

  group('Quote Calculation Engine Tests', () {
    test('QuoteLineItem unitPriceMinor and lineTotalMinor calculation', () {
      final item = QuoteLineItem(
        id: '1',
        kind: 'material',
        description: '200A Panel',
        quantity: 2,
        unitCostMinor: 10000, // $100.00
        markupBps: 2500, // 25% -> $125.00
      );

      expect(item.unitPriceMinor, 12500); // $125.00
      expect(item.lineTotalMinor, 25000); // $250.00
    });

    test('QuoteCalculator calculates subtotal, tax, and optional items correctly', () {
      final items = [
        QuoteLineItem(
          id: '1',
          kind: 'material',
          description: 'Panel',
          quantity: 1,
          unitCostMinor: 10000,
          markupBps: 2000, // $120.00
        ),
        QuoteLineItem(
          id: '2',
          kind: 'labor',
          description: 'Labor',
          quantity: 2,
          unitCostMinor: 5000,
          markupBps: 0, // $100.00
        ),
        QuoteLineItem(
          id: '3',
          kind: 'material',
          description: 'Optional Surge Protector',
          quantity: 1,
          unitCostMinor: 5000,
          markupBps: 0, // $50.00 (optional)
          isOptional: true,
        ),
      ];

      final result = QuoteCalculator.calculate(
        lineItems: items,
        taxRateBps: 1000, // 10% tax
      );

      expect(result.subtotalMinor, 22000); // $120 + $100 = $220.00
      expect(result.taxMinor, 2200); // 10% of $220 = $22.00
      expect(result.totalMinor, 24200); // $220 + $22 = $242.00
      expect(result.optionalSubtotalMinor, 5000); // $50.00
    });
  });

  group('Widget Integration Tests', () {
    // T301b switched this screen from hardcoded mock data to the live
    // `offlineCustomersProvider`, so the test overrides that provider with
    // known data instead of expecting mock names. The old version pumped a
    // screen that now spins on a real gateway call and pumpAndSettle timed out.
    testWidgets('renders customer cards from the data provider', (WidgetTester tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            offlineCustomersProvider.overrideWith(
              (ref) async => [_customer('Johnathan Miller'), _customer('Sarah Jenkins')],
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const CustomerListScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Customer CRM'), findsOneWidget);
      expect(find.text('Johnathan Miller'), findsOneWidget);
      expect(find.text('Sarah Jenkins'), findsOneWidget);
    });

    testWidgets('shows a loading indicator while customers resolve', (WidgetTester tester) async {
      final completer = Completer<List<Customer>>();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            offlineCustomersProvider.overrideWith((ref) => completer.future),
          ],
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const CustomerListScreen(),
          ),
        ),
      );
      await tester.pump(); // one frame: still loading, future unresolved

      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      completer.complete(const []); // let it settle so the test tears down clean
      await tester.pumpAndSettle();
    });
  });
}
