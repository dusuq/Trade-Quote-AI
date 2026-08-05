import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tradequote_mobile/core/database/local_database.dart';
import 'package:tradequote_mobile/core/sync/sync_engine.dart';
import 'package:tradequote_mobile/core/sync/sync_queue.dart';

/// Mirrors LocalDatabase's schema (that method is private) so these tests
/// run against a real in-memory sqlite DB instead of a mocked query layer.
Future<Database> _openTestDb() async {
  sqfliteFfiInit();
  final db = await databaseFactoryFfi.openDatabase(inMemoryDatabasePath);
  final batch = db.batch();

  batch.execute('''
    CREATE TABLE customers (
      id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      name TEXT NOT NULL,
      company_name TEXT NOT NULL DEFAULT '',
      phone TEXT NOT NULL DEFAULT '',
      email TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active',
      tags TEXT NOT NULL DEFAULT '[]',
      updated_at TEXT NOT NULL,
      server_updated_at TEXT
    )
  ''');
  batch.execute('''
    CREATE TABLE customer_properties (
      id TEXT PRIMARY KEY,
      customer_id TEXT NOT NULL,
      address_line1 TEXT NOT NULL DEFAULT '',
      city TEXT NOT NULL DEFAULT '',
      state TEXT NOT NULL DEFAULT '',
      zip_code TEXT NOT NULL DEFAULT '',
      property_type TEXT NOT NULL DEFAULT ''
    )
  ''');
  batch.execute('''
    CREATE TABLE customer_contacts (
      id TEXT PRIMARY KEY,
      customer_id TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT '',
      email TEXT NOT NULL DEFAULT '',
      phone TEXT NOT NULL DEFAULT '',
      role TEXT NOT NULL DEFAULT ''
    )
  ''');
  batch.execute('''
    CREATE TABLE pricebook_items (
      id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      kind TEXT NOT NULL DEFAULT 'material',
      sku TEXT,
      name TEXT NOT NULL,
      description TEXT,
      unit TEXT NOT NULL DEFAULT 'each',
      unit_cost_minor INTEGER NOT NULL DEFAULT 0,
      default_markup_bps INTEGER NOT NULL DEFAULT 0,
      currency TEXT NOT NULL DEFAULT 'USD',
      trade TEXT NOT NULL DEFAULT 'material',
      updated_at TEXT NOT NULL,
      server_updated_at TEXT
    )
  ''');
  batch.execute('''
    CREATE TABLE quotes (
      id TEXT PRIMARY KEY,
      tenant_id TEXT NOT NULL,
      customer_id TEXT NOT NULL,
      customer_name TEXT NOT NULL DEFAULT '',
      number TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'DRAFT',
      tax_rate_bps INTEGER NOT NULL DEFAULT 0,
      current_version INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      server_updated_at TEXT
    )
  ''');
  batch.execute('''
    CREATE TABLE quote_line_items (
      id TEXT PRIMARY KEY,
      quote_id TEXT NOT NULL,
      pricebook_item_id TEXT,
      kind TEXT NOT NULL DEFAULT 'material',
      description TEXT NOT NULL DEFAULT '',
      quantity REAL NOT NULL DEFAULT 1.0,
      unit TEXT NOT NULL DEFAULT 'each',
      unit_cost_minor INTEGER NOT NULL DEFAULT 0,
      markup_bps INTEGER NOT NULL DEFAULT 0,
      is_optional INTEGER NOT NULL DEFAULT 0,
      sort_order INTEGER NOT NULL DEFAULT 0
    )
  ''');
  batch.execute('''
    CREATE TABLE sync_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      action TEXT NOT NULL,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL,
      retry_count INTEGER NOT NULL DEFAULT 0,
      last_error TEXT
    )
  ''');
  batch.execute('''
    CREATE TABLE sync_metadata (
      entity_type TEXT PRIMARY KEY,
      last_synced_at TEXT NOT NULL,
      etag TEXT
    )
  ''');

  await batch.commit(noResult: true);
  return db;
}

void main() {
  late Database db;

  setUp(() async {
    db = await _openTestDb();
  });

  tearDown(() async {
    await db.close();
  });

  group('SyncEngine.pushPendingMutations', () {
    test('a successful push marks the queue entry completed', () async {
      await SyncQueue.enqueue(db,
          entityType: 'customer',
          entityId: 'c1',
          action: 'create',
          payload: {'name': 'Acme'});

      final client =
          MockClient((request) async => http.Response('{"id":"c1"}', 201));
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pushPendingMutations();

      expect(await SyncQueue.pendingCount(db), 0);
    });

    test('a failing push marks the entry failed and keeps it queued',
        () async {
      await SyncQueue.enqueue(db,
          entityType: 'customer',
          entityId: 'c2',
          action: 'update',
          payload: {'name': 'Acme'});

      final client =
          MockClient((request) async => http.Response('server error', 500));
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pushPendingMutations();

      final pending = await SyncQueue.getPending(db);
      expect(pending.single.retryCount, 1);
      expect(pending.single.lastError, contains('500'));
    });

    test('sends the right HTTP verb and path per action', () async {
      final calls = <String>[];
      await SyncQueue.enqueue(db,
          entityType: 'customer',
          entityId: 'c3',
          action: 'delete',
          payload: {});

      final client = MockClient((request) async {
        calls.add('${request.method} ${request.url.path}');
        return http.Response('', 200);
      });
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pushPendingMutations();

      expect(calls, ['DELETE /v1/customers/c3']);
    });
  });

  group('SyncEngine.pullCustomers', () {
    test('inserts a brand-new customer with no local row', () async {
      final client = MockClient((request) async {
        if (request.url.path == '/v1/customers') {
          return http.Response(
              jsonEncode({
                'items': [
                  {
                    'id': 'srv-1',
                    'tenant_id': 't1',
                    'display_name': 'New Co',
                    'updated_at': '2026-08-02T10:00:00Z',
                  }
                ]
              }),
              200);
        }
        return http.Response('[]', 200);
      });
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pullCustomers();

      final customers = await LocalDatabase.getCustomers(db);
      expect(customers.length, 1);
      expect(customers.single['name'], 'New Co');
    });

    test(
        'an existing local row is merged through the conflict resolver, not overwritten blindly',
        () async {
      await LocalDatabase.upsertCustomer(db, {
        'id': 'srv-2',
        'tenant_id': 't1',
        'display_name': 'Server Original',
        'updated_at': '2026-08-02T09:00:00Z',
      });
      // Simulate a later offline edit by hand-updating the local row's
      // updated_at ahead of the server's, as an offline edit path would.
      await db.update(
        'customers',
        {'name': 'Offline Rename', 'updated_at': '2026-08-02T12:00:00Z'},
        where: 'id = ?',
        whereArgs: ['srv-2'],
      );

      final client = MockClient((request) async {
        if (request.url.path == '/v1/customers') {
          return http.Response(
              jsonEncode({
                'items': [
                  {
                    'id': 'srv-2',
                    'tenant_id': 't1',
                    'display_name': 'Server Newer Name',
                    'updated_at': '2026-08-02T11:00:00Z',
                  }
                ]
              }),
              200);
        }
        return http.Response('[]', 200);
      });
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pullCustomers();

      final customers = await LocalDatabase.getCustomers(db);
      expect(customers.single['name'], 'Offline Rename',
          reason:
              'local edit is newer than the server row, so it should win for an editable field');
    });
  });

  group('SyncEngine.pullQuotes — money-safety invariant', () {
    test(
        'a newer offline edit cannot clobber server-authoritative money fields',
        () async {
      await LocalDatabase.upsertQuote(db, {
        'id': 'q-1',
        'tenant_id': 't1',
        'customer_id': 'c1',
        'title': 'Original quote',
        'tax_rate_bps': 750,
        'updated_at': '2026-08-02T09:00:00Z',
      });
      // A stale/incorrect offline total, saved locally with a *newer*
      // updated_at than the server's recomputed value.
      await db.update(
        'quotes',
        {
          'title': 'Offline title edit',
          'tax_rate_bps': 999999,
          'updated_at': '2026-08-02T12:00:00Z',
        },
        where: 'id = ?',
        whereArgs: ['q-1'],
      );

      final client = MockClient((request) async {
        if (request.url.path == '/v1/quotes') {
          return http.Response(
              jsonEncode({
                'items': [
                  {
                    'id': 'q-1',
                    'tenant_id': 't1',
                    'customer_id': 'c1',
                    'title': 'Server title',
                    'tax_rate_bps': 750,
                    'updated_at': '2026-08-02T11:00:00Z',
                    'line_items': [],
                  }
                ]
              }),
              200);
        }
        return http.Response('[]', 200);
      });
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      await engine.pullQuotes();

      final quote = await LocalDatabase.getQuoteById(db, 'q-1');
      expect(quote!['title'], 'Offline title edit',
          reason: 'editable field: newer local edit wins');
      expect(quote['tax_rate_bps'], 750,
          reason:
              'tax_rate_bps is server-authoritative and must never come from a stale offline edit, even when local is newer');
    });
  });

  group('SyncEngine.syncAll re-entrancy', () {
    test('a second concurrent call is a no-op while one is in flight',
        () async {
      var requestCount = 0;
      final client = MockClient((request) async {
        requestCount++;
        await Future.delayed(const Duration(milliseconds: 20));
        return http.Response('[]', 200);
      });
      final engine =
          SyncEngine(baseUrl: 'http://gw.test', token: 't', db: db, client: client);

      final first = engine.syncAll();
      expect(engine.isSyncing, isTrue);
      final second = engine.syncAll();

      await Future.wait([first, second]);

      expect(engine.isSyncing, isFalse);
      // pushPendingMutations (no queue) + 3 pulls = 3 requests for a single
      // run; the second overlapping call must add zero extra requests.
      expect(requestCount, 3);
    });
  });
}
