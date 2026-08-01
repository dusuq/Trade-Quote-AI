import 'dart:convert';

import 'package:sqflite/sqflite.dart';

class SyncQueueEntry {
  final int? id;
  final String entityType;
  final String entityId;
  final String action;
  final Map<String, dynamic> payload;
  final String createdAt;
  final int retryCount;
  final String? lastError;

  SyncQueueEntry({
    this.id,
    required this.entityType,
    required this.entityId,
    required this.action,
    required this.payload,
    required this.createdAt,
    this.retryCount = 0,
    this.lastError,
  });

  factory SyncQueueEntry.fromRow(Map<String, dynamic> row) {
    return SyncQueueEntry(
      id: row['id'] as int?,
      entityType: row['entity_type'] as String,
      entityId: row['entity_id'] as String,
      action: row['action'] as String,
      payload: jsonDecode(row['payload'] as String) as Map<String, dynamic>,
      createdAt: row['created_at'] as String,
      retryCount: row['retry_count'] as int? ?? 0,
      lastError: row['last_error'] as String?,
    );
  }
}

class SyncQueue {
  static Future<void> enqueue(
    Database db, {
    required String entityType,
    required String entityId,
    required String action,
    required Map<String, dynamic> payload,
  }) async {
    await db.insert('sync_queue', {
      'entity_type': entityType,
      'entity_id': entityId,
      'action': action,
      'payload': jsonEncode(payload),
      'created_at': DateTime.now().toIso8601String(),
    });
  }

  static Future<List<SyncQueueEntry>> getPending(Database db) async {
    final rows = await db.query(
      'sync_queue',
      orderBy: 'created_at ASC',
      where: 'retry_count < ?',
      whereArgs: [5],
    );
    return rows.map(SyncQueueEntry.fromRow).toList();
  }

  static Future<int> pendingCount(Database db) async {
    final result =
        await db.rawQuery('SELECT COUNT(*) as cnt FROM sync_queue');
    return Sqflite.firstIntValue(result) ?? 0;
  }

  static Future<void> markCompleted(Database db, int id) async {
    await db.delete('sync_queue', where: 'id = ?', whereArgs: [id]);
  }

  static Future<void> markFailed(
      Database db, int id, String error) async {
    await db.rawUpdate(
      'UPDATE sync_queue SET retry_count = retry_count + 1, last_error = ? WHERE id = ?',
      [error, id],
    );
  }

  static Future<void> removeForEntity(
      Database db, String entityType, String entityId) async {
    await db.delete(
      'sync_queue',
      where: 'entity_type = ? AND entity_id = ?',
      whereArgs: [entityType, entityId],
    );
  }
}
