import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:tradequote_mobile/features/auth/domain/auth_state.dart';

abstract class TokenStore {
  Future<void> save(UserSession session);
  Future<UserSession?> load();
  Future<void> clear();
}

class SecureTokenStore implements TokenStore {
  SecureTokenStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = 'tq_session_v1';

  final FlutterSecureStorage _storage;

  @override
  Future<void> save(UserSession session) async {
    await _storage.write(
      key: _sessionKey,
      value: jsonEncode(session.toJson()),
    );
  }

  @override
  Future<UserSession?> load() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null) return null;
    try {
      return UserSession.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      // Corrupt or pre-migration payload — treat as logged out rather than crash.
      return null;
    }
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _sessionKey);
  }
}
