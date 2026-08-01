import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'package:tradequote_mobile/core/database/local_database.dart';
import 'package:tradequote_mobile/core/sync/conflict_resolver.dart';
import 'package:tradequote_mobile/core/sync/sync_queue.dart';

class SyncEngine {
  final String baseUrl;
  final String? token;
  final Database db;
  bool _syncing = false;

  SyncEngine({
    required this.baseUrl,
    required this.token,
    required this.db,
  });

  bool get isSyncing => _syncing;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<void> syncAll() async {
    if (_syncing) return;
    _syncing = true;
    try {
      await pushPendingMutations();
      await pullCustomers();
      await pullPricebookItems();
      await pullQuotes();
    } finally {
      _syncing = false;
    }
  }

  Future<void> pushPendingMutations() async {
    final entries = await SyncQueue.getPending(db);
    for (final entry in entries) {
      try {
        await _pushEntry(entry);
        await SyncQueue.markCompleted(db, entry.id!);
      } catch (e) {
        await SyncQueue.markFailed(db, entry.id!, e.toString());
      }
    }
  }

  Future<void> _pushEntry(SyncQueueEntry entry) async {
    final path = _pathForEntity(entry.entityType, entry.entityId);
    late http.Response response;

    switch (entry.action) {
      case 'create':
        response = await http.post(
          Uri.parse('$baseUrl$path'),
          headers: _headers,
          body: jsonEncode(entry.payload),
        );
        break;
      case 'update':
        response = await http.put(
          Uri.parse('$baseUrl$path/${entry.entityId}'),
          headers: _headers,
          body: jsonEncode(entry.payload),
        );
        break;
      case 'delete':
        response = await http.delete(
          Uri.parse('$baseUrl$path/${entry.entityId}'),
          headers: _headers,
        );
        break;
      default:
        return;
    }

    if (response.statusCode >= 400) {
      throw Exception('Push failed: ${response.statusCode} ${response.body}');
    }
  }

  String _pathForEntity(String entityType, String entityId) {
    switch (entityType) {
      case 'customer':
        return '/v1/customers';
      case 'pricebook_item':
        return '/v1/pricebook/items';
      case 'quote':
        return '/v1/quotes';
      default:
        return '/v1/$entityType';
    }
  }

  Future<void> pullCustomers() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/customers'),
        headers: _headers,
      );
      if (response.statusCode != 200) return;

      final body = jsonDecode(response.body);
      final List items =
          body is Map ? (body['items'] as List? ?? []) : (body as List);

      for (final item in items) {
        final serverId = item['id'] as String;
        final existing = await db.query('customers',
            where: 'id = ?', whereArgs: [serverId], limit: 1);

        if (existing.isEmpty) {
          await LocalDatabase.upsertCustomer(
              db, item as Map<String, dynamic>);
        } else {
          final localRow = existing.first;
          final existingProps = await db.query('customer_properties',
              where: 'customer_id = ?', whereArgs: [serverId]);
          final existingContacts = await db.query('customer_contacts',
              where: 'customer_id = ?', whereArgs: [serverId]);
          final localMap = {
            ...localRow,
            'properties': existingProps,
            'contacts': existingContacts,
          };
          final resolved = ConflictResolver.resolveScalar(
            local: localMap,
            server: item as Map<String, dynamic>,
            entityType: 'customer',
          );
          await LocalDatabase.upsertCustomer(db, resolved);
        }
      }

      await LocalDatabase.setLastSyncedAt(
          db, 'customers', DateTime.now().toIso8601String());
    } catch (_) {}
  }

  Future<void> pullPricebookItems() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/pricebook/items'),
        headers: _headers,
      );
      if (response.statusCode != 200) return;

      final body = jsonDecode(response.body);
      final List items = body is List ? body : [];

      for (final item in items) {
        await LocalDatabase.upsertPricebookItem(
            db, item as Map<String, dynamic>);
      }

      await LocalDatabase.setLastSyncedAt(
          db, 'pricebook_items', DateTime.now().toIso8601String());
    } catch (_) {}
  }

  Future<void> pullQuotes() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/v1/quotes'),
        headers: _headers,
      );
      if (response.statusCode != 200) return;

      final body = jsonDecode(response.body);
      final List items =
          body is Map ? (body['items'] as List? ?? []) : (body as List);

      for (final item in items) {
        final serverId = item['id'] as String;
        final existingQuote = await LocalDatabase.getQuoteById(db, serverId);

        if (existingQuote == null) {
          await LocalDatabase.upsertQuote(
              db, item as Map<String, dynamic>);
        } else {
          final serverMap = item as Map<String, dynamic>;
          final resolved = ConflictResolver.resolveScalar(
            local: existingQuote,
            server: serverMap,
            entityType: 'quote',
          );

          final localLineItems =
              (existingQuote['line_items'] as List?)
                  ?.cast<Map<String, dynamic>>() ??
              [];
          final serverLineItems =
              (serverMap['line_items'] as List?)
                  ?.cast<Map<String, dynamic>>() ??
              [];

          if (localLineItems.isNotEmpty || serverLineItems.isNotEmpty) {
            resolved['line_items'] = ConflictResolver.mergeLineItems(
              local: localLineItems,
              server: serverLineItems,
            );
          }

          await LocalDatabase.upsertQuote(db, resolved);
        }
      }

      await LocalDatabase.setLastSyncedAt(
          db, 'quotes', DateTime.now().toIso8601String());
    } catch (_) {}
  }
}

final syncEngineProvider = Provider<SyncEngine?>((ref) {
  return null;
});
