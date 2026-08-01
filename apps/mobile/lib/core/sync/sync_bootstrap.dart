import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tradequote_mobile/core/connectivity/connectivity_provider.dart';
import 'package:tradequote_mobile/core/database/local_database.dart';
import 'package:tradequote_mobile/core/sync/sync_engine.dart';
import 'package:tradequote_mobile/features/auth/domain/auth_state.dart';

class SyncBootstrap {
  final Ref ref;
  SyncEngine? _engine;
  Timer? _periodicSync;

  SyncBootstrap(this.ref);

  Future<void> start() async {
    final session = ref.read(authProvider);
    if (session == null) return;

    final db = await LocalDatabase.database;
    _engine = SyncEngine(
      baseUrl: 'http://10.0.2.2:8000',
      token: session.accessToken,
      db: db,
    );

    await _engine!.syncAll();

    _periodicSync?.cancel();
    _periodicSync = Timer.periodic(const Duration(minutes: 5), (_) async {
      final connectivity = ref.read(connectivityProvider);
      if (connectivity.isOnline) {
        await _engine?.syncAll();
        ref.read(connectivityProvider.notifier).refreshPendingCount();
      }
    });
  }

  Future<void> syncNow() async {
    final connectivity = ref.read(connectivityProvider);
    if (!connectivity.isOnline) return;
    await _engine?.syncAll();
    ref.read(connectivityProvider.notifier).refreshPendingCount();
  }

  void stop() {
    _periodicSync?.cancel();
    _engine = null;
  }
}

final syncBootstrapProvider = Provider<SyncBootstrap>((ref) {
  final bootstrap = SyncBootstrap(ref);

  final session = ref.watch(authProvider);
  if (session != null) {
    bootstrap.start();
  } else {
    bootstrap.stop();
  }

  ref.onDispose(() => bootstrap.stop());
  return bootstrap;
});
