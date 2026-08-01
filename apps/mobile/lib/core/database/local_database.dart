import 'dart:convert';

import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class LocalDatabase {
  static const _dbName = 'tradequote.db';
  static const _dbVersion = 1;

  static Database? _database;

  static Future<Database> get database async {
    _database ??= await _initDatabase();
    return _database!;
  }

  static Future<Database> _initDatabase() async {
    final dir = await getApplicationDocumentsDirectory();
    final path = join(dir.path, _dbName);
    return openDatabase(
      path,
      version: _dbVersion,
      onCreate: _onCreate,
    );
  }

  static Future<void> _onCreate(Database db, int version) async {
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
        property_type TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
      )
    ''');

    batch.execute('''
      CREATE TABLE customer_contacts (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        role TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
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
        sort_order INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE
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

    batch.execute(
        'CREATE INDEX idx_sync_queue_entity ON sync_queue(entity_type, entity_id)');
    batch.execute(
        'CREATE INDEX idx_quote_line_items_quote ON quote_line_items(quote_id)');
    batch.execute(
        'CREATE INDEX idx_customer_properties_customer ON customer_properties(customer_id)');
    batch.execute(
        'CREATE INDEX idx_customer_contacts_customer ON customer_contacts(customer_id)');

    await batch.commit(noResult: true);
  }

  // --- Customer CRUD ---

  static Future<void> upsertCustomer(
      Database db, Map<String, dynamic> customer) async {
    final tags = customer['tags'];
    final row = {
      'id': customer['id'],
      'tenant_id': customer['tenant_id'] ?? '',
      'name': customer['display_name'] ?? customer['name'] ?? '',
      'company_name': customer['company_name'] ?? '',
      'phone': customer['phone'] ?? '',
      'email': customer['email'] ?? '',
      'status': customer['status'] ?? 'active',
      'tags': tags is List ? jsonEncode(tags) : '[]',
      'updated_at': DateTime.now().toIso8601String(),
      'server_updated_at': customer['updated_at'],
    };
    await db.insert('customers', row,
        conflictAlgorithm: ConflictAlgorithm.replace);

    final id = customer['id'] as String;
    await db.delete('customer_properties',
        where: 'customer_id = ?', whereArgs: [id]);
    await db.delete('customer_contacts',
        where: 'customer_id = ?', whereArgs: [id]);

    final props = customer['properties'] as List?;
    if (props != null) {
      for (final p in props) {
        await db.insert('customer_properties', {
          'id': p['id'],
          'customer_id': id,
          'address_line1': p['address_line1'] ?? '',
          'city': p['city'] ?? '',
          'state': p['state'] ?? '',
          'zip_code': p['zip_code'] ?? '',
          'property_type': p['property_type'] ?? '',
        });
      }
    }

    final contacts = customer['contacts'] as List?;
    if (contacts != null) {
      for (final c in contacts) {
        await db.insert('customer_contacts', {
          'id': c['id'],
          'customer_id': id,
          'name': c['name'] ?? '',
          'email': c['email'] ?? '',
          'phone': c['phone'] ?? '',
          'role': c['role'] ?? '',
        });
      }
    }
  }

  static Future<List<Map<String, dynamic>>> getCustomers(Database db) async {
    final rows = await db.query('customers', orderBy: 'name ASC');
    final result = <Map<String, dynamic>>[];
    for (final row in rows) {
      final id = row['id'] as String;
      final props = await db.query('customer_properties',
          where: 'customer_id = ?', whereArgs: [id]);
      final contacts = await db.query('customer_contacts',
          where: 'customer_id = ?', whereArgs: [id]);
      result.add({
        ...row,
        'tags': jsonDecode(row['tags'] as String? ?? '[]'),
        'properties': props,
        'contacts': contacts,
      });
    }
    return result;
  }

  // --- Pricebook CRUD ---

  static Future<void> upsertPricebookItem(
      Database db, Map<String, dynamic> item) async {
    final row = {
      'id': item['id'],
      'tenant_id': item['tenant_id'] ?? '',
      'kind': item['kind'] ?? 'material',
      'sku': item['sku'],
      'name': item['name'],
      'description': item['description'],
      'unit': item['unit'] ?? 'each',
      'unit_cost_minor': item['unit_cost_minor'] ?? 0,
      'default_markup_bps': item['default_markup_bps'] ?? 0,
      'currency': item['currency'] ?? 'USD',
      'trade': item['trade'] ?? item['kind'] ?? 'material',
      'updated_at': DateTime.now().toIso8601String(),
      'server_updated_at': item['updated_at'],
    };
    await db.insert('pricebook_items', row,
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  static Future<List<Map<String, dynamic>>> getPricebookItems(
      Database db) async {
    return db.query('pricebook_items', orderBy: 'name ASC');
  }

  // --- Quote CRUD ---

  static Future<void> upsertQuote(
      Database db, Map<String, dynamic> quote) async {
    final row = {
      'id': quote['id'],
      'tenant_id': quote['tenant_id'] ?? '',
      'customer_id': quote['customer_id'] ?? '',
      'customer_name': quote['customer_name'] ?? '',
      'number': quote['number'] ?? '',
      'title': quote['title'] ?? '',
      'status': quote['status'] ?? 'DRAFT',
      'tax_rate_bps': quote['tax_rate_bps'] ?? 0,
      'current_version': quote['current_version'] ?? 1,
      'created_at': quote['created_at'] ?? DateTime.now().toIso8601String(),
      'updated_at': DateTime.now().toIso8601String(),
      'server_updated_at': quote['updated_at'],
    };
    await db.insert('quotes', row,
        conflictAlgorithm: ConflictAlgorithm.replace);

    final id = quote['id'] as String;
    await db.delete('quote_line_items',
        where: 'quote_id = ?', whereArgs: [id]);

    final lineItems = quote['line_items'] as List?;
    if (lineItems != null) {
      for (final li in lineItems) {
        await db.insert('quote_line_items', {
          'id': li['id'],
          'quote_id': id,
          'pricebook_item_id': li['pricebook_item_id'],
          'kind': li['kind'] ?? 'material',
          'description': li['description'] ?? '',
          'quantity': (li['quantity'] as num?)?.toDouble() ?? 1.0,
          'unit': li['unit'] ?? 'each',
          'unit_cost_minor': li['unit_cost_minor'] ?? 0,
          'markup_bps': li['markup_bps'] ?? 0,
          'is_optional': (li['is_optional'] == true) ? 1 : 0,
          'sort_order': li['sort_order'] ?? 0,
        });
      }
    }
  }

  static Future<List<Map<String, dynamic>>> getQuotes(Database db) async {
    final rows = await db.query('quotes', orderBy: 'created_at DESC');
    final result = <Map<String, dynamic>>[];
    for (final row in rows) {
      final id = row['id'] as String;
      final lineItems = await db.query('quote_line_items',
          where: 'quote_id = ?',
          whereArgs: [id],
          orderBy: 'sort_order ASC');
      result.add({
        ...row,
        'line_items': lineItems
            .map((li) => {
                  ...li,
                  'is_optional': (li['is_optional'] as int?) == 1,
                })
            .toList(),
      });
    }
    return result;
  }

  static Future<Map<String, dynamic>?> getQuoteById(
      Database db, String id) async {
    final rows =
        await db.query('quotes', where: 'id = ?', whereArgs: [id], limit: 1);
    if (rows.isEmpty) return null;
    final lineItems = await db.query('quote_line_items',
        where: 'quote_id = ?', whereArgs: [id], orderBy: 'sort_order ASC');
    return {
      ...rows.first,
      'line_items': lineItems
          .map((li) => {
                ...li,
                'is_optional': (li['is_optional'] as int?) == 1,
              })
          .toList(),
    };
  }

  // --- Sync Metadata ---

  static Future<String?> getLastSyncedAt(
      Database db, String entityType) async {
    final rows = await db.query('sync_metadata',
        where: 'entity_type = ?', whereArgs: [entityType], limit: 1);
    if (rows.isEmpty) return null;
    return rows.first['last_synced_at'] as String?;
  }

  static Future<void> setLastSyncedAt(
      Database db, String entityType, String timestamp) async {
    await db.insert(
      'sync_metadata',
      {'entity_type': entityType, 'last_synced_at': timestamp},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  static Future<void> clearAll(Database db) async {
    await db.delete('sync_queue');
    await db.delete('sync_metadata');
    await db.delete('quote_line_items');
    await db.delete('quotes');
    await db.delete('customer_properties');
    await db.delete('customer_contacts');
    await db.delete('customers');
    await db.delete('pricebook_items');
  }
}
