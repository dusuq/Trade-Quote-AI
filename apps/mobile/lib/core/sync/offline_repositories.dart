import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite/sqflite.dart';
import 'package:tradequote_mobile/core/database/local_database.dart';
import 'package:tradequote_mobile/core/network/api_client.dart';
import 'package:tradequote_mobile/core/sync/sync_queue.dart';
import 'package:tradequote_mobile/features/customers/domain/customer.dart';
import 'package:tradequote_mobile/features/pricebook/domain/pricebook_item.dart';

final offlineCustomersProvider =
    FutureProvider<List<Customer>>((ref) async {
  final db = await LocalDatabase.database;
  final api = ref.watch(apiClientProvider);

  // Try fetching from server first, persist locally
  try {
    final data = await api.get('/v1/customers');
    final List items =
        data is Map ? (data['items'] as List? ?? []) : (data as List);
    for (final item in items) {
      await LocalDatabase.upsertCustomer(db, item as Map<String, dynamic>);
    }
    await LocalDatabase.setLastSyncedAt(
        db, 'customers', DateTime.now().toIso8601String());
  } catch (_) {
    // Offline — fall through to local data
  }

  final localRows = await LocalDatabase.getCustomers(db);
  return localRows.map((row) => Customer.fromJson(row)).toList();
});

final offlinePricebookProvider =
    FutureProvider<List<PricebookItem>>((ref) async {
  final db = await LocalDatabase.database;
  final api = ref.watch(apiClientProvider);

  try {
    final data = await api.get('/v1/pricebook/items');
    if (data is List) {
      for (final item in data) {
        await LocalDatabase.upsertPricebookItem(
            db, item as Map<String, dynamic>);
      }
      await LocalDatabase.setLastSyncedAt(
          db, 'pricebook_items', DateTime.now().toIso8601String());
    }
  } catch (_) {}

  final localRows = await LocalDatabase.getPricebookItems(db);
  return localRows.map((row) => PricebookItem.fromJson(row)).toList();
});

class OfflineQuoteRepository {
  static Future<void> saveQuote(
    Database db, {
    required Map<String, dynamic> quoteData,
    bool isNew = true,
  }) async {
    await LocalDatabase.upsertQuote(db, quoteData);
    await SyncQueue.enqueue(
      db,
      entityType: 'quote',
      entityId: quoteData['id'] as String,
      action: isNew ? 'create' : 'update',
      payload: quoteData,
    );
  }
}
