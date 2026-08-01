import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:tradequote_mobile/core/database/local_database.dart';
import 'package:tradequote_mobile/core/sync/sync_queue.dart';

class ConnectivityState {
  final bool isOnline;
  final int pendingSyncCount;

  const ConnectivityState({
    required this.isOnline,
    required this.pendingSyncCount,
  });

  const ConnectivityState.initial()
      : isOnline = true,
        pendingSyncCount = 0;
}

class ConnectivityNotifier extends StateNotifier<ConnectivityState> {
  StreamSubscription<List<ConnectivityResult>>? _subscription;
  Timer? _pendingCountTimer;

  ConnectivityNotifier() : super(const ConnectivityState.initial()) {
    _init();
  }

  Future<void> _init() async {
    final results = await Connectivity().checkConnectivity();
    final online = !results.contains(ConnectivityResult.none);
    state = ConnectivityState(
      isOnline: online,
      pendingSyncCount: state.pendingSyncCount,
    );

    _subscription = Connectivity().onConnectivityChanged.listen((results) {
      final online = !results.contains(ConnectivityResult.none);
      state = ConnectivityState(
        isOnline: online,
        pendingSyncCount: state.pendingSyncCount,
      );
    });

    _pendingCountTimer =
        Timer.periodic(const Duration(seconds: 10), (_) => refreshPendingCount());
  }

  Future<void> refreshPendingCount() async {
    try {
      final db = await LocalDatabase.database;
      final count = await SyncQueue.pendingCount(db);
      state = ConnectivityState(
        isOnline: state.isOnline,
        pendingSyncCount: count,
      );
    } catch (_) {}
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _pendingCountTimer?.cancel();
    super.dispose();
  }
}

final connectivityProvider =
    StateNotifierProvider<ConnectivityNotifier, ConnectivityState>(
  (ref) => ConnectivityNotifier(),
);
