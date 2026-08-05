import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:tradequote_mobile/core/sync/sync_queue.dart';

Future<Database> _openTestDb() async {
  sqfliteFfiInit();
  final db = await databaseFactoryFfi.openDatabase(inMemoryDatabasePath);
  await db.execute('''
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

  test('enqueue then getPending returns the entry in FIFO order', () async {
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c1',
        action: 'create',
        payload: {'name': 'Acme'});
    await Future.delayed(const Duration(milliseconds: 5));
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c2',
        action: 'create',
        payload: {'name': 'Beta'});

    final pending = await SyncQueue.getPending(db);
    expect(pending.length, 2);
    expect(pending[0].entityId, 'c1');
    expect(pending[1].entityId, 'c2');
    expect(pending[0].payload, {'name': 'Acme'});
    expect(pending[0].retryCount, 0);
  });

  test('getPending excludes entries that hit the retry ceiling', () async {
    await SyncQueue.enqueue(db,
        entityType: 'quote',
        entityId: 'q1',
        action: 'update',
        payload: {});
    final pending = await SyncQueue.getPending(db);
    final id = pending.single.id!;

    for (var i = 0; i < 5; i++) {
      await SyncQueue.markFailed(db, id, 'network error $i');
    }

    final afterFailures = await SyncQueue.getPending(db);
    expect(afterFailures, isEmpty,
        reason: 'retry_count reached 5, entry must drop out of pending');
  });

  test('markFailed increments retry_count and records lastError', () async {
    await SyncQueue.enqueue(db,
        entityType: 'quote',
        entityId: 'q2',
        action: 'update',
        payload: {});
    final id = (await SyncQueue.getPending(db)).single.id!;

    await SyncQueue.markFailed(db, id, 'timeout');

    final pending = await SyncQueue.getPending(db);
    expect(pending.single.retryCount, 1);
    expect(pending.single.lastError, 'timeout');
  });

  test('markCompleted removes the row entirely', () async {
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c3',
        action: 'delete',
        payload: {});
    final id = (await SyncQueue.getPending(db)).single.id!;

    await SyncQueue.markCompleted(db, id);

    expect(await SyncQueue.getPending(db), isEmpty);
    expect(await SyncQueue.pendingCount(db), 0);
  });

  test('removeForEntity clears only that entity\'s queued entries', () async {
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c4',
        action: 'update',
        payload: {});
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c5',
        action: 'update',
        payload: {});

    await SyncQueue.removeForEntity(db, 'customer', 'c4');

    final pending = await SyncQueue.getPending(db);
    expect(pending.length, 1);
    expect(pending.single.entityId, 'c5');
  });

  test('pendingCount reflects the number of queued rows', () async {
    expect(await SyncQueue.pendingCount(db), 0);
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c6',
        action: 'create',
        payload: {});
    await SyncQueue.enqueue(db,
        entityType: 'customer',
        entityId: 'c7',
        action: 'create',
        payload: {});
    expect(await SyncQueue.pendingCount(db), 2);
  });
}
